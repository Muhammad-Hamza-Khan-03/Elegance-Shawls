"""A thin handle on the migrated PostgreSQL database for ingestion/route tests."""
from sqlalchemy import func, select, text, update

from models.relational_model import IngestionJob, Product, StagedProduct
from repositories import jobs as jobs_repo


class Db:
    def __init__(self, sessions):
        self.sessions = sessions

    async def create_job(self, path, source_id="primary", **kwargs):
        async with self.sessions() as session, session.begin():
            return await jobs_repo.create_job(session, source_id=source_id, path=path, **kwargs)

    async def jobs(self, **where) -> list[IngestionJob]:
        stmt = select(IngestionJob).order_by(IngestionJob.created_at, IngestionJob.id)
        for name, value in where.items():
            stmt = stmt.where(getattr(IngestionJob, name) == value)
        async with self.sessions() as session:
            return list((await session.execute(stmt)).scalars())

    async def job(self, **where) -> IngestionJob | None:
        found = await self.jobs(**where)
        return found[0] if found else None

    async def staged(self, **where) -> list[StagedProduct]:
        stmt = select(StagedProduct).order_by(StagedProduct.created_at, StagedProduct.id)
        for name, value in where.items():
            stmt = stmt.where(getattr(StagedProduct, name) == value)
        async with self.sessions() as session:
            return list((await session.execute(stmt)).scalars())

    async def staged_one(self, **where) -> StagedProduct | None:
        found = await self.staged(**where)
        return found[0] if found else None

    async def products(self) -> list[Product]:
        async with self.sessions() as session:
            return list((await session.execute(select(Product).order_by(Product.created_at))).scalars())

    async def count(self, table: str) -> int:
        async with self.sessions() as session:
            return (await session.execute(text(f"select count(*) from {table}"))).scalar()

    async def set_jobs(self, values: dict, **where) -> None:
        stmt = update(IngestionJob).values(**values)
        for name, value in where.items():
            stmt = stmt.where(getattr(IngestionJob, name) == value)
        async with self.sessions() as session, session.begin():
            await session.execute(stmt)

    async def set_staged(self, values: dict, **where) -> None:
        stmt = update(StagedProduct).values(**values)
        for name, value in where.items():
            stmt = stmt.where(getattr(StagedProduct, name) == value)
        async with self.sessions() as session, session.begin():
            await session.execute(stmt)

    async def clear(self) -> None:
        async with self.sessions() as session, session.begin():
            await session.execute(text("TRUNCATE staged_product_audit, staged_products, ingestion_jobs, variants, products RESTART IDENTITY CASCADE"))

    async def snapshot(self) -> dict:
        """Everything in the three tables, for 'nothing was written' assertions."""
        async with self.sessions() as session:
            result = {}
            for table in ("products", "variants", "ingestion_jobs", "staged_products", "staged_product_audit"):
                rows = (await session.execute(text(f"select * from {table} order by 1"))).mappings().all()
                result[table] = [dict(r) for r in rows]
            return result
