"""Hybrid retrieval: lexical + vector candidates fused by fixed Reciprocal Rank Fusion, read-only.

The deterministic parser and `catalog.search.evaluate` stay the authority for every hard constraint (active, category,
material, colour, price, stock, one variant satisfying all variant-level constraints). Only products that pass them are
ever candidates, so neither a lexical overlap nor an embedding can make an ineligible product eligible. The free-text
words, which are all-required in deterministic search, only feed the lexical branch here.

  eligible (exact filters, at most `max_scan` rows examined)
    -> lexical top K  (words matched, then catalogue order)   -> rank l
    -> semantic top K (cosine distance, live vectors only)    -> rank s     (omitted when unavailable)
  score = 1/(RRF_K + l) + 1/(RRF_K + s), an absent branch adding 0; order (score, created_at, id) descending.

Branch ranks are internal. Paging is a stateless keyset on that order: every page recomputes the same bounded fusion,
and the opaque cursor carries the last (score, created_at, id) plus a hash of query, filters, limits and search/index
version. Tradeoff: a page is exact only within the candidate window (<= 2K products); data that changes between pages can
move items across the cursor, so a client may see a product late or twice, never one that is ineligible.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from catalog.query import ParsedQuery, Vocabulary, normalize
from catalog.search import BATCH, MAX_LIMIT, Fetch, Hit, evaluate, key, product_words
from models.relational_model import ProductEmbedding, VariantEmbedding
from repositories import embeddings as emb_repo
from search import embedding_service as svc
from search import local_e5
from search.providers import EmbeddingError, EmbeddingProvider, embed_checked, provider_for
from search.representations import REPRESENTATION_VERSION

RRF_K = 60  # fixed by contract; not configurable and not client-selectable
SEARCH_VERSION = "hybrid-rrf60-v1"
CURSOR_MAX_LENGTH = 512
Position = tuple[float, datetime, uuid.UUID]                       # (rrf_score, created_at, id) of the last returned item
Semantic = Callable[[list[Hit], int], Awaitable[dict[uuid.UUID, float]]]   # eligible hits, K -> {product id: cosine distance}


# ---- fusion (pure) ----------------------------------------------------------------------------

def rrf_score(lexical_rank: int | None, semantic_rank: int | None) -> float:
    """Ranks are 1-based; None means the branch did not return the product. Rounded so cursor round-trips are exact."""
    return round(sum(1 / (RRF_K + r) for r in (lexical_rank, semantic_rank) if r is not None), 12)


def lexical_ranking(q: ParsedQuery, hits: list[Hit], k: int) -> list[Hit]:
    """Eligible hits holding at least one query word (all of them when the query has no free words), best first."""
    if not q.text:
        scored = [(0, h) for h in hits]
    else:
        scored = [(n, h) for h in hits if (n := len(product_words(h.product) & set(q.text)))]
    scored.sort(key=lambda t: key(t[1].product), reverse=True)     # catalogue order first, then the stable sort by overlap
    scored.sort(key=lambda t: -t[0])
    return [h for _, h in scored[:k]]


def semantic_ranking(hits: list[Hit], distances: dict[uuid.UUID, float], k: int) -> list[Hit]:
    """Hits that have a distance, nearest first, catalogue order breaking ties. Unknown ids are ignored."""
    found = sorted((h for h in hits if h.product.id in distances), key=lambda h: key(h.product), reverse=True)
    found.sort(key=lambda h: distances[h.product.id])
    return found[:k]


def fuse(lexical: list[Hit], semantic: list[Hit]) -> list[tuple[float, Hit]]:
    """Union by product id (deduplicated), scored and ordered by (score, created_at, id) descending."""
    ranks: dict[uuid.UUID, list] = {}
    for slot, branch in enumerate((lexical, semantic)):
        for rank, hit in enumerate(branch, 1):
            entry = ranks.setdefault(hit.product.id, [hit, None, None])
            if entry[1 + slot] is None:
                entry[1 + slot] = rank
    scored = [(rrf_score(l, s), hit) for hit, l, s in ranks.values()]
    scored.sort(key=lambda t: (t[0], *key(t[1].product)), reverse=True)
    return scored


# ---- cursor -----------------------------------------------------------------------------------

def _checksum(payload: bytes) -> str:
    return hashlib.sha256(b"elegance-hybrid-cursor-v1:" + payload).hexdigest()[:16]


def query_hash(q: str, parsed: ParsedQuery, k_lexical: int, k_semantic: int, max_scan: int) -> str:
    """Normalised query + applied filters + bounds: a cursor only continues the search that produced it."""
    raw = json.dumps([normalize(q).split(), parsed.filters(), list(parsed.text), k_lexical, k_semantic, max_scan],
                     sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def encode_cursor(position: Position, *, version: str, qhash: str) -> str:
    score, created_at, row_id = position
    payload = json.dumps({"h": 1, "ver": version, "q": qhash, "s": repr(score),
                          "c": created_at.astimezone(timezone.utc).isoformat(timespec="microseconds"), "i": str(row_id)},
                         sort_keys=True, separators=(",", ":")).encode()
    return f"{base64.urlsafe_b64encode(payload).decode().rstrip('=')}.{_checksum(payload)}"


def decode_cursor(cursor: str, *, version: str, qhash: str) -> Position:
    """ValueError for anything malformed, tampered, from another query/filter set, or from another search/index version."""
    try:
        if not isinstance(cursor, str) or not cursor or len(cursor) > CURSOR_MAX_LENGTH:
            raise ValueError
        body, dot, checksum = cursor.partition(".")
        if not dot or "." in checksum:
            raise ValueError
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        if not hmac.compare_digest(checksum, _checksum(payload)):
            raise ValueError
        data = json.loads(payload)
        if not isinstance(data, dict) or set(data) != {"h", "ver", "q", "s", "c", "i"} or data["h"] != 1:
            raise ValueError
        if data["ver"] != version or data["q"] != qhash:
            raise ValueError
        created_at, row_id, score = datetime.fromisoformat(data["c"]), uuid.UUID(data["i"]), float(data["s"])
        if created_at.tzinfo is None or str(row_id) != data["i"] or not 0 < score < 1:
            raise ValueError
        return score, created_at.astimezone(timezone.utc), row_id
    except Exception as exc:
        raise ValueError("Invalid cursor") from exc


def search_version(provider: EmbeddingProvider | None, index_version: str) -> str:
    """Names everything that changes the ranking, so a cursor cannot cross a model or index change."""
    revision = getattr(provider, "model_revision", "")
    semantic = f"{provider.name}/{provider.model}/{index_version}" + (f"/{revision}" if revision else "") if provider else "lexical-only"
    return f"{SEARCH_VERSION}|{semantic}"


# ---- retrieval --------------------------------------------------------------------------------

async def eligible_hits(fetch: Fetch, q: ParsedQuery, *, vocab: Vocabulary | None = None, max_scan: int,
                        batch: int = BATCH) -> list[Hit]:
    """Every product passing the exact hard filters among at most `max_scan` examined rows, catalogue order.
    `q` must already carry no free words (they are not constraints here)."""
    hits: list[Hit] = []
    scanned, last = 0, None
    while scanned < max_scan:
        n = min(batch, max_scan - scanned)
        rows = await fetch(last, n)
        for product in rows:
            scanned += 1
            last = key(product)
            if hit := evaluate(q, product, vocab):
                hits.append(hit)
        if len(rows) < n:
            break
    return hits


async def hybrid_page(fetch: Fetch, parsed: ParsedQuery, semantic: Semantic | None, *, limit: int = 20,
                      after: Position | None = None, k_lexical: int, k_semantic: int, max_scan: int,
                      vocab: Vocabulary | None = None, batch: int = BATCH) -> tuple[list[Hit], Position | None]:
    """(one page of hits, position to continue after or None). Unsupported queries return nothing, like deterministic search."""
    limit = max(1, min(limit, MAX_LIMIT))
    if parsed.unsupported:
        return [], None
    hits = await eligible_hits(fetch, replace(parsed, text=()), vocab=vocab, max_scan=max_scan, batch=batch)
    lexical = lexical_ranking(parsed, hits, k_lexical)
    near = semantic_ranking(hits, await semantic(hits, k_semantic), k_semantic) if semantic and hits else []
    fused = fuse(lexical, near)
    if after is not None:
        fused = [(s, h) for s, h in fused if (s, *key(h.product)) < after]
    page = fused[:limit]
    last = page[-1] if page else None
    return [h for _, h in page], ((last[0], *key(last[1].product)) if len(fused) > limit and last else None)


async def query_vector(text: str, *, enabled: bool, name: str, dimensions: int) -> tuple[EmbeddingProvider | None, list[float] | None]:
    """(provider, query vector) from the local fake or, when explicitly flagged, local_e5; (None, None) when disabled,
    unconfigured, blank or failing (the caller then ranks lexically)."""
    if not enabled or not text.strip():
        return None, None
    try:
        if name == "local_e5":
            provider = await asyncio.to_thread(local_e5.local_provider, "query")   # first call loads the model
            if dimensions != provider.dimensions:
                return None, None
        else:
            provider = provider_for(name, dimensions)
        return provider, (await embed_checked(provider, [text.strip()]))[0]
    except EmbeddingError:
        return None, None


def semantic_from_database(session: AsyncSession, provider: EmbeddingProvider, vector: list[float], index_version: str) -> Semantic:
    """Cosine-nearest live vectors of the eligible products (variant vectors only for their satisfying variants).
    Each row is re-checked against the live source, so a vector whose content changed is dropped at once.
    shortcut: stale rows are dropped after the top-K query, so a page can hold fewer than K; refill if staleness gets common."""
    ident = {"representation_version": REPRESENTATION_VERSION, "provider": provider.name, "model": provider.model,
             "model_revision": getattr(provider, "model_revision", ""), "index_version": index_version}

    async def run(hits: list[Hit], k: int) -> dict[uuid.UUID, float]:
        distances: dict[uuid.UUID, float] = {}
        for kind, model in (("product", ProductEmbedding), ("variant", VariantEmbedding)):
            owners = [h.product.id for h in hits] if kind == "product" else [v for h in hits for v in h.variant_ids]
            distance = model.embedding.cosine_distance(vector)
            stmt = (emb_repo.active_select(kind, **ident).add_columns(distance.label("d"))
                    .where((model.product_id if kind == "product" else model.variant_id).in_(owners))
                    .order_by(distance, model.id).limit(k))
            for row, d in (await session.execute(stmt)).all():
                owner_id = row.product_id if kind == "product" else row.variant_id
                if svc._matches(await svc.load_source(session, kind, owner_id), row):
                    distances[row.product_id] = min(d, distances.get(row.product_id, d))
        return distances

    return run
