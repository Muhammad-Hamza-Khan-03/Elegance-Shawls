"""Hybrid (keyword + semantic) public product search. Callers own the transaction; nothing is committed here.

Both candidate lists are built INSIDE the same hard filters (public visibility and the single-variant
colour/price/stock EXISTS), so ranking can reorder products but never admit one the filters exclude. Fusion is
weighted RRF (semantic.fusion). The ranking is a bounded window: at most MAX_CANDIDATES per list, so results beyond
the fused window are unreachable, and pages are offsets into that window (a catalogue change between page requests
can shift later pages; keyset stability only exists in the lexical fallback). Embeddings whose hash no longer
matches the product's current public text are excluded, exactly like embeddings.servable_product_ids.
"""
import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Sequence

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.relational_model import Product, ProductEmbedding, Variant
from repositories import products as catalogue
from repositories.embeddings import Target, _on, _product_dict
from repositories.products import VariantFilter
from semantic.fusion import FusionWeights, fuse
from semantic.representation import RepresentationError, represent

MAX_CANDIDATES = 200
MAX_TERMS = 8


def binding(q: str, variant: VariantFilter | None, target: Target, weights: FusionWeights) -> str:
    """Identifies the query a cursor was issued for; a cursor replayed against anything else is refused."""
    doc = {"q": q, "variant": asdict(variant) if variant else None, "target": asdict(target), "w": asdict(weights)}
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:16]


def _lexical_score(terms: Sequence[str]):
    """Field-weighted hit count: name 4, slug/item number 3, material/variant 2, description 1."""
    total = 0
    for term in terms:
        like = catalogue.like_pattern(term)
        hit = lambda col, w: case((col.ilike(like, escape="\\"), w), else_=0)  # noqa: E731
        in_variant = (select(func.count()).where(Variant.product_id == Product.id, (Variant.name.ilike(like, escape="\\")
                      | Variant.color.ilike(like, escape="\\"))).scalar_subquery())
        total = (total + hit(Product.name, 4) + hit(Product.slug, 3) + hit(Product.item_number, 3)
                 + hit(Product.material, 2) + case((in_variant > 0, 2), else_=0) + hit(Product.main_description, 1))
    return total


async def hybrid_ids(session: AsyncSession, *, q: str, query_vector: Sequence[float], target: Target,
                     variant: VariantFilter | None, weights: FusionWeights) -> tuple[list[uuid.UUID], dict[uuid.UUID, Product]]:
    """Fused, deterministically ordered product ids (best first) and the Product rows behind them."""
    hard = [Product.status == "active"] + ([catalogue._variant_match(variant)] if variant else [])
    terms = q.split()[:MAX_TERMS]

    lexical = (select(Product).where(*hard, *(catalogue._term_match(t) for t in terms))
               .order_by(_lexical_score(terms).desc(), Product.created_at.desc(), Product.id.desc())
               .limit(MAX_CANDIDATES))
    products = {p.id: p for p in (await session.execute(lexical)).scalars()}
    keyword = list(products)

    distance = ProductEmbedding.embedding.cosine_distance(list(query_vector))
    semantic_stmt = (select(ProductEmbedding.content_hash, Product)
                     .join(Product, Product.id == ProductEmbedding.product_id)
                     .where(*hard, _on(target, ProductEmbedding), ProductEmbedding.product_revision == Product.revision,
                            ProductEmbedding.dimensions == len(query_vector))
                     .order_by(distance, Product.id).limit(MAX_CANDIDATES))
    semantic = []
    for stored_hash, product in (await session.execute(semantic_stmt)).all():
        try:
            fresh = represent(_product_dict(product))["fingerprint"] == stored_hash
        except RepresentationError:
            fresh = False
        if fresh:
            products.setdefault(product.id, product)
            semantic.append(product.id)

    created: dict[uuid.UUID, datetime] = {pid: p.created_at for pid, p in products.items()}
    return fuse(keyword, semantic, created, weights), products


def page_of(ids: list[uuid.UUID], products: dict[uuid.UUID, Product], offset: int, limit: int) -> tuple[list[Product], int | None]:
    """(items, next offset or None when the window is exhausted)."""
    window = ids[offset:offset + limit]
    return [products[i] for i in window], (offset + limit if offset + limit < len(ids) else None)
