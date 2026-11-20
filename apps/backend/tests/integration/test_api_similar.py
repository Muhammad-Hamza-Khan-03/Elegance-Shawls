import asyncio

from tests.integration.repo_helpers import product_input, tx
from repositories import products as repo
from repositories.products import VariantInput


def v(color):
    return VariantInput(name=color, color=color, image_url="https://img.example/x.jpg", price=1000, stock=1)


def test_similar_is_same_category_active_ranked_and_excludes_self(pg_engine_factory):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async def go():
        engine = pg_engine_factory()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with tx(sessions) as s:
                base = await repo.create_product(s, product_input("base", variants=[v("Brown")]))
                match = await repo.create_product(s, product_input("match", variants=[v("Brown")]))
                other = await repo.create_product(s, product_input("other", variants=[v("Green")]))
                stole = await repo.create_product(s, product_input("stole", category="stoles", variants=[v("Brown")]))
                for p in (base, match, other, stole):
                    await repo.set_status(s, p.id, "active", enforce_review=False)
            async with sessions() as s:
                found = await repo.similar_candidates(s, base, 50)
            return {p.slug for p in found}
        finally:
            await engine.dispose()

    assert asyncio.run(go()) == {"match", "other"}   # not itself, not the other category
