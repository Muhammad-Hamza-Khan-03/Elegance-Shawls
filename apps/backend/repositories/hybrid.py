"""Hybrid keyword + semantic product search over PostgreSQL. Callers own the transaction (read-only here).

Both sources are filtered in SQL by the same predicates the lexical catalogue uses: publicly active product and,
when requested, ONE variant satisfying colour/price/stock together. A semantic hit therefore never bypasses
them. Semantic is used only with a configured embedder and only over fresh embeddings; if there is no embedder,
the query is blank, or embedding fails / returns an invalid vector, the result is lexical-only (`mode`
says which), never an error and never a guess. Each source contributes at most POOL candidates
(shortcut: the pool bounds recall and pages beyond it end, raise POOL or add an ANN index when the catalogue outgrows it).
"""
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.relational_model import Product, ProductEmbedding
from repositories.embeddings import Target, _on, _product_dict
from repositories.products import VariantFilter, _term_match, _variant_match
from semantic.embeddings import validate_vector
from semantic.ranking import Candidate, Weights, fuse, lexical_score, normalize_weights, page_after
from semantic.representation import REPRESENTATION_VERSION, RepresentationError, represent
from utils.pagination import decode_ranked_cursor, encode_ranked_cursor

POOL = 200
MAX_TERMS = 8
DEFAULT_WEIGHTS = normalize_weights(1, 1)


@dataclass
class HybridPage:
    items: list[Product]
    next_cursor: str | None
    mode: str  # "hybrid" | "lexical"


def _binding(mode: str, terms: list[str], variant: VariantFilter | None, weights: Weights, target: Target | None,
             max_distance: float | None = None) -> str:
    doc = [mode, terms, vars(variant) if variant else None, [weights.lexical, weights.semantic],
           [target.provider, target.model, target.representation_version] if target else None, POOL]
    if max_distance is not None:
        doc.append(max_distance)  # appended only when set, so existing cursors stay valid
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:16]


def _query_vector(embedder: Any, q: str):
    """(vector, target) or None when semantic search is unavailable for this request."""
    if embedder is None:
        return None
    try:
        config = embedder.config
        return validate_vector(embedder.embed(q), config.dimensions), Target(config.provider, config.model, REPRESENTATION_VERSION)
    except Exception:  # provider failure of any kind degrades to lexical
        return None


async def hybrid_search(session: AsyncSession, *, q: str | None, limit: int, cursor: str | None = None,
                        variant: VariantFilter | None = None, embedder: Any = None,
                        weights: Weights = DEFAULT_WEIGHTS, max_distance: float | None = None) -> HybridPage:
    """Fused ranking, one page. A bad/foreign cursor raises ValueError (callers answer 400)."""
    terms = (q or "").split()[:MAX_TERMS]
    semantic = _query_vector(embedder, " ".join(terms)) if terms else None
    target = semantic[1] if semantic else None
    mode = "hybrid" if semantic else "lexical"
    binding = _binding(mode, [t.casefold() for t in terms], variant, weights, target, max_distance)
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
        vector, tgt = semantic
        dist = ProductEmbedding.embedding.cosine_distance(list(vector))
        sem = (select(Product, ProductEmbedding.content_hash, dist).join(ProductEmbedding, ProductEmbedding.product_id == Product.id)
               .where(Product.status == "active", _on(tgt, ProductEmbedding), ProductEmbedding.dimensions == len(vector),
                      ProductEmbedding.product_revision == Product.revision))
        if variant is not None:
            sem = sem.where(_variant_match(variant))
        for p, stored, d in (await session.execute(sem.order_by(dist, Product.id).limit(POOL))).all():
            try:
                fresh = stored == represent(_product_dict(p))["fingerprint"]
            except RepresentationError:
                fresh = False
            if fresh and d is not None and d == d and d != float("inf") and (max_distance is None or d <= max_distance):  # drops stale, NaN (zero vector), inf and too-far neighbours
                products[p.id] = p
                cands[p.id] = Candidate(p.id, p.created_at, cands[p.id].lexical if p.id in cands else None, float(d))

    rows, more = page_after(fuse(list(cands.values()), weights), after, limit)
    next_cursor = None
    if more and rows:
        score, last = rows[-1]
        next_cursor = encode_ranked_cursor((score, last.created_at, last.id), binding)
    return HybridPage([products[c.id] for _, c in rows], next_cursor, mode)
