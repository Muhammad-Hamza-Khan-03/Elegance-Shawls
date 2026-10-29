"""Catalogue attributes: read and idempotent bulk upsert. Callers own the transaction (no commits here)."""
import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import case, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.attributes import SOURCE_RANK, Attribute
from models.relational_model import CatalogAttribute

CHUNK = 1000  # rows per INSERT: well under the driver's bind-parameter limit
_VALUES = ("value", "source", "model_version", "approved_by", "approved_at")


async def list_attributes(session: AsyncSession, product_ids: Sequence[uuid.UUID]) -> list[CatalogAttribute]:
    """Product-level and variant-level attributes of the given products, in a stable order."""
    if not product_ids:
        return []
    stmt = (select(CatalogAttribute).where(CatalogAttribute.product_id.in_(product_ids))
            .order_by(CatalogAttribute.product_id, CatalogAttribute.variant_id.nulls_first(), CatalogAttribute.key))
    return list((await session.execute(stmt)).scalars())


async def get_attribute(session: AsyncSession, product_id: uuid.UUID, key: str, variant_id: uuid.UUID | None = None):
    stmt = select(CatalogAttribute).where(CatalogAttribute.product_id == product_id, CatalogAttribute.key == key)
    stmt = stmt.where(CatalogAttribute.variant_id.is_(None) if variant_id is None else CatalogAttribute.variant_id == variant_id)
    return (await session.execute(stmt)).scalar_one_or_none()


def _rank(column):
    return case(SOURCE_RANK, value=column)


async def upsert_attributes(session: AsyncSession, attributes: Iterable[Attribute]) -> int:
    """Insert or update by (product, variant, key); returns rows inserted or changed.

    An existing row is replaced only by a source of equal or higher trust (staff_approved > supplier_declared >
    visual_suggestion > imported) and only when something differs, so reruns neither downgrade approved values
    nor churn timestamps. Duplicates inside one call: the last wins.
    """
    unique = {(a.product_id, a.variant_id, a.key): a for a in attributes}
    changed = 0
    for product_level in (True, False):
        rows = [a for a in unique.values() if (a.variant_id is None) == product_level]
        for i in range(0, len(rows), CHUNK):
            stmt = insert(CatalogAttribute).values([
                {"product_id": a.product_id, "variant_id": a.variant_id, "key": a.key, **{c: getattr(a, c) for c in _VALUES}}
                for a in rows[i:i + CHUNK]])
            new = stmt.excluded
            differs = tuple_(*(getattr(CatalogAttribute, c) for c in _VALUES)).is_distinct_from(
                tuple_(*(getattr(new, c) for c in _VALUES)))
            stmt = stmt.on_conflict_do_update(
                index_elements=["product_id", "key"] if product_level else ["variant_id", "key"],
                index_where=CatalogAttribute.variant_id.is_(None) if product_level else CatalogAttribute.variant_id.is_not(None),
                set_={**{c: getattr(new, c) for c in _VALUES}, "updated_at": func.now()},
                where=(_rank(new.source) >= _rank(CatalogAttribute.source)) & differs,
            ).returning(CatalogAttribute.id)
            changed += len((await session.execute(stmt)).all())
    return changed
