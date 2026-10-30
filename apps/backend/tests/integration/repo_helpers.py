"""Helpers for repository integration tests (real PostgreSQL). Engines are created inside each test's loop."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from repositories.products import ProductInput, VariantInput

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def run_repo(factory, scenario):
    """Run `async def scenario(sessions)` against the migrated database; `sessions()` opens a new session."""
    async def go():
        engine = factory()
        try:
            return await scenario(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()

    return asyncio.run(go())


@asynccontextmanager
async def tx(sessions):
    """One session = one committed transaction (rolled back if the body raises)."""
    async with sessions() as session, session.begin():
        yield session


async def count(sessions, table: str, where: str = "true") -> int:
    async with sessions() as session:
        return (await session.execute(text(f"select count(*) from {table} where {where}"))).scalar()


def product_input(slug="classic-pashmina", **over) -> ProductInput:
    variants = over.pop("variants", None) or [VariantInput(name="Burgundy", image_url="https://img.example/b.jpg", price=4500, stock=4)]
    return ProductInput(slug=slug, name=over.pop("name", "Classic Pashmina"),
                        cover_image_url="https://img.example/c.jpg", variants=variants, **over)


def draft(slug="classic-staged", **over) -> dict:
    """The normalised staged `product` document the ingestion pipeline produces."""
    return {"name": "Classic Staged", "slug": slug, "cover_image_url": "https://img.example/c.jpg",
            "images": ["https://img.example/c.jpg"], "main_description": "Soft wool.", "category": "shawls",
            "material": "Wool", "sizing": "Free Size", "weight": None,
            "variants": [{"name": "Burgundy", "color": "Burgundy", "size": "Free Size", "image_url": "https://img.example/b.jpg", "stock": 0},
                         {"name": "Black", "color": "Black", "size": "Free Size", "image_url": "https://img.example/k.jpg", "stock": 0}],
            **over}


def stage_kwargs(n=1, **over) -> dict:
    return {"source_id": "primary", "source_name": "Primary", "source_url": f"https://source.example/p/{n}",
            "source_product_id": str(n), "source_content_hash": f"hash-{n}", "fetched_at": NOW,
            "ingestion_job_id": None, "source_price": 29.5, "source_currency": "USD", "product": draft(f"staged-{n}"),
            "source_attributes": {"origin": "Kashmir"}, "missing_fields": ["price", "stock"], **over}
