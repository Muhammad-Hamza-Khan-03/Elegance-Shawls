"""Deterministic, idempotent backfill of catalogue attributes from existing catalogue columns (offline: no network).

  python scripts/backfill_catalog_attributes.py [--batch-size 500]      # uses DATABASE_URL
Run from apps/backend. Reads products/variants only; writes catalog_attributes only. Safe to rerun.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from catalog.attributes import derive_attributes  # noqa: E402
from models.relational_model import Product, Variant  # noqa: E402
from repositories.attributes import upsert_attributes  # noqa: E402

BATCH = 500


async def backfill(sessions: async_sessionmaker, batch_size: int = BATCH) -> dict[str, int]:
    """Keyset-paged by product id; each batch is its own transaction, so memory is bounded and a failure loses one batch."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    totals = {"products": 0, "written": 0}
    after = None
    while True:
        async with sessions() as session, session.begin():
            stmt = select(Product.id, Product.material).order_by(Product.id).limit(batch_size)
            products = (await session.execute(stmt.where(Product.id > after) if after else stmt)).all()
            if not products:
                return totals
            ids = [p.id for p in products]
            by_product: dict = {i: [] for i in ids}
            for v in (await session.execute(select(Variant.product_id, Variant.id, Variant.color)
                                            .where(Variant.product_id.in_(ids)).order_by(Variant.product_id, Variant.position))):
                by_product[v.product_id].append((v.id, v.color))
            rows = [a for p in products for a in derive_attributes(p.id, p.material, by_product[p.id])]
            totals["written"] += await upsert_attributes(session, rows)
        totals["products"] += len(products)
        after = ids[-1]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=BATCH)
    args = parser.parse_args()
    from database.pg import make_engine, postgres_configured

    if not postgres_configured():
        print("DATABASE_URL is not set")
        return 2
    engine = make_engine()
    try:
        print(await backfill(async_sessionmaker(engine, expire_on_commit=False), args.batch_size))
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
