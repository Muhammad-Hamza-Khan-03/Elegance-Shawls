"""Catalogue image vectors and nearest-product search. Takes an AsyncSession and never commits."""
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.relational_model import Product, Variant, VariantImageEmbedding


@dataclass(frozen=True)
class Match:
    product_id: uuid.UUID
    name: str
    slug: str
    colour: str | None
    price: int
    currency: str
    similarity: float


async def existing_hash(session: AsyncSession, variant_id: uuid.UUID, model: str) -> str | None:
    return (await session.execute(select(VariantImageEmbedding.image_hash).where(
        VariantImageEmbedding.variant_id == variant_id, VariantImageEmbedding.model == model))).scalar_one_or_none()


async def upsert(session: AsyncSession, variant_id: uuid.UUID, model: str, image_hash: str, vector: list[float]) -> None:
    stmt = pg_insert(VariantImageEmbedding).values(variant_id=variant_id, model=model, image_hash=image_hash, embedding=vector)
    await session.execute(stmt.on_conflict_do_update(constraint="uq_variant_image_embeddings_variant_id_model",
                                                     set_={"image_hash": image_hash, "embedding": vector}))


async def nearest(session: AsyncSession, vector: list[float], model: str, limit: int, min_similarity: float) -> list[Match]:
    """Best buyable variant per product, most similar first. Only active, in-stock, priced variants of active products."""
    similarity = (1 - VariantImageEmbedding.embedding.cosine_distance(vector)).label("similarity")
    rows = (await session.execute(
        select(Product.id, Product.name, Product.slug, Variant.color, Variant.price, Variant.currency, similarity)
        .join(Variant, Variant.id == VariantImageEmbedding.variant_id).join(Product, Product.id == Variant.product_id)
        .where(VariantImageEmbedding.model == model, Product.status == "active", Variant.is_active.is_(True), Variant.stock > 0, Variant.price.is_not(None))
        .order_by(similarity.desc()).limit(limit * 6))).all()
    best: dict[uuid.UUID, Match] = {}
    for pid, name, slug, colour, price, currency, sim in rows:
        if sim >= min_similarity and pid not in best:
            best[pid] = Match(pid, name, slug, colour, price, currency, float(sim))
    return list(best.values())[:limit]
