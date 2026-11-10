"""Deterministic SYNTHETIC catalogue for the real-stack E2E suite (frontend/e2e-real). Idempotent; development only.

  DATABASE_URL=postgresql+asyncpg://... ENVIRONMENT=development python scripts/seed_e2e.py

The fixtures encode the cases the specs assert: an in-stock brown stole under 4000, a brown stole over 4000, a brown shawl over budget, an
out-of-stock stole, a one-unit variant (stock revalidation) and a draft product that must never be public.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from database.pg import make_engine  # noqa: E402
from repositories import Conflict, products as repo  # noqa: E402

IMG = "https://picsum.photos/seed/{}/600/800"


def product(slug, name, category, material, colour, price, stock, status="active", description=""):
    return repo.ProductInput(
        slug=slug, name=name, cover_image_url=IMG.format(slug), images=[IMG.format(slug)], category=category,
        main_description=description or f"{name}. Synthetic E2E fixture.", material=material, sizing="70 x 200 cm", weight="250 g",
        item_number=f"E2E-{slug[:12]}", status=status, price=price,
        variants=[repo.VariantInput(name=colour, color=colour, image_url=IMG.format(slug + "-v"), price=price, stock=stock)])


FIXTURES = [
    product("e2e-brown-pashmina-stole", "Brown Pashmina Stole", "stoles", "Pashmina blend", "Brown", 3500, 5),
    product("e2e-brown-jamawar-stole", "Brown Jamawar Stole", "stoles", "Jamawar wool", "Brown", 4500, 3),   # over the 4000 budget: makes the budget filter discriminating
    product("e2e-brown-wool-shawl", "Brown Wool Shawl", "shawls", "Merino wool", "Brown", 5200, 3),
    product("e2e-maroon-silk-stole", "Maroon Silk Stole", "stoles", "Silk blend", "Maroon", 2900, 0),
    product("e2e-ivory-merino-shawl", "Ivory Merino Shawl", "shawls", "Merino wool", "Ivory", 4200, 8),
    product("e2e-last-piece-scarf", "Last Piece Scarf", "scarves", "Cotton modal", "Blue", 1800, 1),
    product("e2e-draft-green-shawl", "Draft Green Shawl", "shawls", "Merino wool", "Green", 3900, 4, status="draft"),
]


async def main() -> None:
    if os.environ.get("ENVIRONMENT", "development") != "development":
        raise SystemExit("seed_e2e.py only runs with ENVIRONMENT=development")
    engine = make_engine(os.environ["DATABASE_URL"])
    sessions, created = async_sessionmaker(engine, expire_on_commit=False), 0
    for fixture in FIXTURES:
        async with sessions() as session:
            try:
                async with session.begin():
                    await repo.create_product(session, fixture)
                created += 1
            except Conflict:
                pass
    await engine.dispose()
    print(f"seeded {created} new e2e products ({len(FIXTURES) - created} already present)")


if __name__ == "__main__":
    asyncio.run(main())
