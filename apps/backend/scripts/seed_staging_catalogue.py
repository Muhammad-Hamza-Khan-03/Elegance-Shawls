"""Create disposable active catalogue rows for isolated staging semantic-search QA.

This script is intentionally opt-in and idempotent. It must never be enabled against production.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from configuration.config import settings  # noqa: E402
from database.pg import make_engine, postgres_configured  # noqa: E402
from models.relational_model import Product  # noqa: E402

SEED = (
    {
        "slug": "staging-silver-grey-pashmina-shawl",
        "name": "Staging Silver Grey Pashmina Shawl",
        "material": "Pashmina wool",
        "main_description": "A soft silver grey pashmina shawl for weddings and formal evenings.",
        "price": 24369,
    },
    {
        "slug": "staging-black-embroidered-wool-shawl",
        "name": "Staging Black Embroidered Wool Shawl",
        "material": "Wool",
        "main_description": "A black embroidered wool shawl with a warm hand-finished weave.",
        "price": 18900,
    },
    {
        "slug": "staging-ivory-silk-shawl",
        "name": "Staging Ivory Silk Shawl",
        "material": "Silk blend",
        "main_description": "An ivory silk blend shawl designed for bridal and festive wear.",
        "price": 27900,
    },
    {
        "slug": "staging-urdu-rang-shawl",
        "name": "Staging Rangon Wali Shawl",
        "material": "Pashmina",
        "main_description": "خوبصورت رنگوں والی نرم پشمینہ شال، شادی اور تہوار کے لیے۔",
        "price": 21500,
    },
)


async def main() -> int:
    if settings.environment.strip().lower() != "staging":
        print("refusing synthetic seed outside staging", file=sys.stderr)
        return 2
    if not postgres_configured():
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    engine = make_engine()
    created = 0
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session, session.begin():
            for item in SEED:
                exists = await session.scalar(select(Product.id).where(Product.slug == item["slug"]))
                if exists:
                    continue
                session.add(Product(category="shawls", status="active", cover_image_url="https://example.invalid/staging/placeholder.jpg", images=[], currency="PKR", sizing="Free Size", weight="Staging", item_number=item["slug"], **item))
                created += 1
    finally:
        await engine.dispose()
    print({"seeded": created, "total_candidates": len(SEED)})
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
