"""Seed a LOCAL database with a synthetic catalogue (no scraping, no real brand data). Idempotent: existing slugs are skipped.

  DATABASE_URL=postgresql+asyncpg://... python scripts/seed_local.py [--count 36]

Refuses to run unless ENVIRONMENT is development, so it cannot fill a shared database by accident.
"""
import argparse
import asyncio
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from database.pg import make_engine  # noqa: E402
from repositories import Conflict, products as repo  # noqa: E402

KINDS = [("shawls", "Shawl", "Pashmina blend", "70 x 200 cm"), ("shawls", "Wool Shawl", "Merino wool", "100 x 200 cm"),
         ("stoles", "Stole", "Silk blend", "50 x 180 cm"), ("scarves", "Scarf", "Cotton modal", "70 x 180 cm")]
COLOURS = ["Red", "Blue", "Brown", "Gray", "Black", "Green", "Camel", "Maroon", "Beige", "Pink"]
# What each fabric is actually for, so descriptions carry real season/warmth signal instead of "warm" on everything.
USE = {"Pashmina blend": "Soft and very warm, made for cold winter days.", "Merino wool": "Thick, cosy merino wool for freezing winter weather.",
       "Silk blend": "Light, airy and breathable, ideal for summer evenings.", "Cotton modal": "Lightweight and cool, comfortable in hot weather."}
STYLES = ["Embroidered", "Plain", "Printed", "Checked", "Fringed", "Jacquard"]


def build(index: int, rng: random.Random) -> repo.ProductInput:
    category, noun, material, sizing = KINDS[index % len(KINDS)]
    style, base = STYLES[index % len(STYLES)], COLOURS[index % len(COLOURS)]
    slug = f"{style}-{base}-{noun}-{index:02d}".lower().replace(" ", "-")
    image = f"https://picsum.photos/seed/{slug}/600/800"
    price = rng.choice([1800, 2400, 2900, 3500, 4200, 5600, 7500])
    colours = [base, *rng.sample([c for c in COLOURS if c != base], rng.choice([0, 1, 2]))]
    variants = [repo.VariantInput(name=c, color=c, image_url=f"https://picsum.photos/seed/{slug}-{c.lower()}/600/800",
                                  price=price + 300 * n, stock=0 if (index + n) % 7 == 0 else rng.randint(1, 9))
                for n, c in enumerate(colours)]
    return repo.ProductInput(slug=slug, name=f"{style} {base} {noun}", cover_image_url=image, images=[image], category=category,
                             main_description=f"A {style.lower()} {noun.lower()} in {base.lower()}. {USE[material]}",
                             material=material, sizing=sizing, weight="250 g", item_number=f"SEED-{index:03d}", status="active",
                             price=price, variants=variants)


async def main(count: int) -> None:
    if os.environ.get("ENVIRONMENT", "development") != "development":
        raise SystemExit("seed_local.py only runs with ENVIRONMENT=development")
    engine = make_engine(os.environ["DATABASE_URL"])
    sessions, rng, created = async_sessionmaker(engine, expire_on_commit=False), random.Random(7), 0
    for i in range(count):
        async with sessions() as session:
            try:
                async with session.begin():
                    await repo.create_product(session, build(i, rng))
                created += 1
            except Conflict:
                pass
    await engine.dispose()
    print(f"seeded {created} new products ({count - created} already present)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=36)
    asyncio.run(main(parser.parse_args().count))
