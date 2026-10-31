"""Hybrid keyword + semantic product search over PostgreSQL. Callers own the transaction (read-only here).

Both sources are filtered in SQL by the same predicates the lexical catalogue uses: publicly active product and,
when requested, ONE variant satisfying colour/price/stock together. A semantic hit therefore never bypasses
them. Vectors come from the canonical embedding tables (product_embeddings / variant_embeddings, written by
search.embedding_service), only rows for the active provider/model/revision/index and whose content hash still
matches the live catalogue. If there is no query embedding (disabled, blank, provider failure) the result is
lexical-only (`mode` says which), never an error and never a guess. Each source contributes at most POOL candidates
(shortcut: the pool bounds recall and pages beyond it end, raise POOL or add an ANN index when the catalogue outgrows it).
"""
import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from models.relational_model import Product, ProductEmbedding, VariantEmbedding
from repositories import embeddings as emb_repo
from repositories.products import VariantFilter, _term_match, _variant_match
from search import embedding_service as svc
from search.hybrid import query_vector, search_version
from search.providers import EmbeddingProvider
from search.representations import REPRESENTATION_VERSION
from semantic.query_parser import has_shopping_signal
from semantic.ranking import Candidate, Weights, fuse, lexical_score, normalize_weights, page_after
from utils.pagination import decode_ranked_cursor, encode_ranked_cursor

POOL = 200
MAX_TERMS = 8
DEFAULT_WEIGHTS = normalize_weights(1, 1)


@dataclass
class HybridPage:
    items: list[Product]
    next_cursor: str | None
    mode: str  # "hybrid" | "lexical"


@dataclass(frozen=True)
class QueryEmbedding:
    provider: EmbeddingProvider
    vector: list[float]


async def embed_query(text: str) -> QueryEmbedding | None:
    """The query vector from the configured canonical provider, or None (lexical-only) when disabled or failing."""
    provider, vector = await query_vector(text, enabled=settings.embedding_enabled, name=settings.embedding_provider,
                                          dimensions=settings.embedding_dimensions)
    return QueryEmbedding(provider, vector) if provider is not None and vector is not None else None


def distance_cutoff(text: str) -> float | None:
    """Max semantic distance to trust. None when the query names something we sell; otherwise only close neighbours count,
    so "delivery kitne din" or "iphone" returns nothing instead of the nearest shawls."""
    return None if has_shopping_signal(text) else settings.semantic_max_distance


def _binding(mode: str, terms: list[str], variant: VariantFilter | None, weights: Weights, version: str | None,
             max_distance: float | None = None) -> str:
    doc = [mode, terms, vars(variant) if variant else None, [weights.lexical, weights.semantic], version, POOL]
    if max_distance is not None:
        doc.append(max_distance)  # appended only when set, so existing cursors stay valid
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:16]


async def _semantic_distances(session: AsyncSession, q: QueryEmbedding, variant: VariantFilter | None,
                              max_distance: float | None) -> dict:
    """{product id: nearest cosine distance} over fresh product and variant vectors of eligible products."""
    ident = {"representation_version": REPRESENTATION_VERSION, "provider": q.provider.name, "model": q.provider.model,
             "model_revision": getattr(q.provider, "model_revision", ""), "index_version": settings.embedding_index_version}
    out: dict = {}
    for kind, model in (("product", ProductEmbedding), ("variant", VariantEmbedding)):
        dist = model.embedding.cosine_distance(q.vector)
        stmt = emb_repo.active_select(kind, **ident).add_columns(dist.label("d"))
        if variant is not None:
            stmt = stmt.where(_variant_match(variant).correlate(Product))  # the variant-kind query already holds a Variant
        rows = (await session.execute(stmt.order_by(dist, model.id).limit(settings.hybrid_semantic_k))).all()
        for row, d in rows:
            if d is None or d != d or d == float("inf") or (max_distance is not None and d > max_distance):
                continue  # NaN (zero vector), inf and too-far neighbours
            owner = row.product_id if kind == "product" else row.variant_id
            if svc._matches(await svc.load_source(session, kind, owner), row):  # drops vectors whose content changed
                out[row.product_id] = min(float(d), out.get(row.product_id, float(d)))
    return out


async def hybrid_search(session: AsyncSession, *, q: str | None, limit: int, cursor: str | None = None,
                        variant: VariantFilter | None = None, embedding: QueryEmbedding | None = None,
                        weights: Weights = DEFAULT_WEIGHTS, max_distance: float | None = None) -> HybridPage:
    """Fused ranking, one page. A bad/foreign cursor raises ValueError (callers answer 400)."""
    terms = (q or "").split()[:MAX_TERMS]
    semantic = embedding if terms else None
    mode = "hybrid" if semantic else "lexical"
    version = search_version(semantic.provider, settings.embedding_index_version) if semantic else None
    binding = _binding(mode, [t.casefold() for t in terms], variant, weights, version, max_distance)
    after = decode_ranked_cursor(cursor, binding) if cursor else None

    stmt = select(Product).where(Product.status == "active")
    if terms:
        stmt = stmt.where(and_(*(_term_match(t) for t in terms)))
    if variant is not None:
        stmt = stmt.where(_variant_match(variant))
    lexical = (await session.execute(stmt.order_by(Product.created_at.desc(), Product.id.desc()).limit(POOL))).scalars().all()
    products = {p.id: p for p in lexical}
    cands = {p.id: Candidate(p.id, p.created_at, lexical=lexical_score(terms, {
        "name": p.name, "item_number": p.item_number, "slug": p.slug, "material": p.material,
        "main_description": p.main_description}, [t for v in p.variants if v.is_active for t in (v.name, v.color)]))
        for p in lexical}

    if semantic:
        near = await _semantic_distances(session, semantic, variant, max_distance)
        missing = [pid for pid in near if pid not in products]
        if missing:
            for p in (await session.execute(select(Product).where(Product.id.in_(missing), Product.status == "active"))).scalars():
                products[p.id] = p
        for pid, d in near.items():
            if pid in products:
                p = products[pid]
                cands[pid] = Candidate(pid, p.created_at, cands[pid].lexical if pid in cands else None, d)

    rows, more = page_after(fuse(list(cands.values()), weights), after, limit)
    next_cursor = None
    if more and rows:
        score, last = rows[-1]
        next_cursor = encode_ranked_cursor((score, last.created_at, last.id), binding)
    return HybridPage([products[c.id] for _, c in rows], next_cursor, mode)
