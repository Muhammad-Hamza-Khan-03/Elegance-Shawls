"""P1-S2: catalog_attributes schema, upsert and backfill against a real PostgreSQL."""
import asyncio
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from catalog.attributes import Attribute
from repositories import attributes as repo
from repositories import products as products_repo
from repositories.products import VariantInput
from tests.integration.conftest import alembic_config
from tests.integration.repo_helpers import count, product_input, run_repo, tx
from tests.integration.test_catalogue_schema import table_names

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backfill_catalog_attributes.py"
spec = importlib.util.spec_from_file_location("backfill_catalog_attributes", SCRIPT)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def variants(*colors):
    return [VariantInput(name=f"V{i}", image_url="https://img.example/v.jpg", price=4000, stock=2, color=c)
            for i, c in enumerate(colors)]


async def make(sessions, slug="p1", material=None, colors=("Black",)):
    async with tx(sessions) as s:
        return await products_repo.create_product(s, product_input(slug, material=material, variants=variants(*colors)))


async def state(sessions):
    async with sessions() as s:
        rows = await s.execute(text("select product_id, variant_id, key, value, source, model_version, approved_by, "
                                    "created_at, updated_at from catalog_attributes order by product_id, variant_id nulls first, key"))
        return [tuple(r) for r in rows]


async def catalogue_state(sessions):
    async with sessions() as s:
        return [tuple(r) for r in await s.execute(text(
            "select p.id, p.status, p.price, p.revision, p.updated_at, v.id, v.stock, v.price from products p "
            "join variants v on v.product_id = p.id order by p.id, v.position"))] + [
            tuple(r) for r in await s.execute(text("select count(*) from outbox"))]


def test_backfill_is_idempotent_deterministic_and_changes_no_product_state(pg_engine_factory):
    async def scenario(sessions):
        a = await make(sessions, "a", "Pashmina", ("Black", "Neela", "Mystery"))
        await make(sessions, "b", None, ("Black and White",))
        before = await catalogue_state(sessions)
        first = await script.backfill(sessions, batch_size=1)
        rows1 = await state(sessions)
        second = await script.backfill(sessions, batch_size=1)
        rows2 = await state(sessions)
        return a, first, second, rows1, rows2, before == await catalogue_state(sessions)

    a, first, second, rows1, rows2, untouched = run_repo(pg_engine_factory, scenario)
    assert first == {"products": 2, "written": 6} and second == {"products": 2, "written": 0}
    assert rows1 == rows2 and untouched                                  # stable counts, content and timestamps
    values = {(r[2], r[3]) for r in rows1 if r[0] == a.id}
    assert values == {("fabric", "pashmina"), ("color_name", "black"), ("color_name", "blue"), ("color_name", None)}
    assert all(r[4] == "imported" and r[5] == "catalog-vocab-1" for r in rows1)
    assert [r[3] for r in rows1 if r[0] != a.id] == [None, None]         # unresolved/ambiguous stay explicit unknown


def test_backfill_preserves_approved_and_supplier_values_and_refreshes_imported(pg_engine_factory):
    async def scenario(sessions):
        p = await make(sessions, "a", "Silk", ("Black", "Red"))
        v0, v1 = p.variants[0].id, p.variants[1].id
        async with tx(sessions) as s:
            await repo.upsert_attributes(s, [
                Attribute(p.id, "fabric", "linen", "staff_approved", approved_by="admin", approved_at=NOW),
                Attribute(p.id, "color_name", "charcoal", "supplier_declared", variant_id=v0),
                Attribute(p.id, "color_name", "crimson", "visual_suggestion", variant_id=v1, model_version="m-1"),
            ])
        await script.backfill(sessions)
        await script.backfill(sessions)
        async with sessions() as s:
            got = {(a.variant_id, a.key): (a.value, a.source) for a in await repo.list_attributes(s, [p.id])}
        return p.id, v0, v1, got

    p, v0, v1, got = run_repo(pg_engine_factory, scenario)
    assert got == {(None, "fabric"): ("linen", "staff_approved"), (v0, "color_name"): ("charcoal", "supplier_declared"),
                   (v1, "color_name"): ("crimson", "visual_suggestion")}


def test_upsert_is_deterministic_and_higher_trust_wins(pg_engine_factory):
    async def scenario(sessions):
        p = await make(sessions)
        v = p.variants[0].id
        async with tx(sessions) as s:
            assert await repo.upsert_attributes(s, [Attribute(p.id, "fabric", "wool", "imported"),
                                                    Attribute(p.id, "fabric", "silk", "imported")]) == 1   # last duplicate wins
            assert await repo.upsert_attributes(s, [Attribute(p.id, "fabric", "silk", "imported")]) == 0   # no-op, no churn
            assert await repo.upsert_attributes(s, [Attribute(p.id, "fabric", "cotton", "supplier_declared")]) == 1
            assert await repo.upsert_attributes(s, [Attribute(p.id, "fabric", "wool", "imported")]) == 0     # lower trust ignored
            assert await repo.upsert_attributes(s, [Attribute(p.id, "fabric", None, "visual_suggestion", model_version="m")]) == 0
            assert await repo.upsert_attributes(s, [Attribute(p.id, "color_name", "red", "imported", variant_id=v)]) == 1
            return (await repo.get_attribute(s, p.id, "fabric")).value, (await repo.get_attribute(s, p.id, "color_name", v)).value, \
                await repo.get_attribute(s, p.id, "color_name")

    assert run_repo(pg_engine_factory, scenario) == ("cotton", "red", None)   # product vs variant level are distinct rows


def raw_insert(sessions, **over):
    values = {"p": None, "v": None, "key": "fabric", "value": "silk", "source": "imported", "by": None, "at": None, **over}

    async def go():
        async with tx(sessions) as s:
            await s.execute(text("insert into catalog_attributes (product_id, variant_id, key, value, source, approved_by, approved_at) "
                                 "values (:p, :v, :key, :value, :source, :by, :at)"), values)
    return go()


@pytest.mark.parametrize("bad", [
    dict(key="price"), dict(source="llm"), dict(value=""), dict(source="staff_approved"),
    dict(by="admin", at=NOW),                                    # approval on a non-staff source
])
def test_database_rejects_invalid_keys_provenance_and_values(pg_engine_factory, bad):
    async def scenario(sessions):
        p = await make(sessions)
        with pytest.raises(IntegrityError):
            await raw_insert(sessions, p=p.id, **bad)
        assert await count(sessions, "catalog_attributes") == 0

    run_repo(pg_engine_factory, scenario)


def test_database_rejects_duplicates_orphans_and_cross_product_variants(pg_engine_factory):
    async def scenario(sessions):
        a, b = await make(sessions, "a"), await make(sessions, "b")
        await raw_insert(sessions, p=a.id)
        await raw_insert(sessions, p=a.id, v=a.variants[0].id)                          # same key, different level: fine
        for dup in (dict(p=a.id), dict(p=a.id, v=a.variants[0].id)):
            with pytest.raises(IntegrityError):
                await raw_insert(sessions, **dup)
        with pytest.raises(IntegrityError):                                              # product does not exist
            await raw_insert(sessions, p="00000000-0000-4000-8000-000000000000")
        with pytest.raises(IntegrityError):                                              # variant of another product
            await raw_insert(sessions, p=b.id, v=a.variants[0].id)
        async with tx(sessions) as s:                                                    # deleting the owner cascades
            await s.execute(text("delete from products where id = :p"), {"p": a.id})
        return await count(sessions, "catalog_attributes")

    assert run_repo(pg_engine_factory, scenario) == 0


def test_migration_downgrade_removes_only_this_schema_and_upgrade_restores_it(pg_url, migrated_url, pg_engine_factory):
    config = alembic_config(pg_url)
    assert "catalog_attributes" in table_names(pg_url)
    try:
        command.downgrade(config, "0006")
        assert "catalog_attributes" not in table_names(pg_url) and {"products", "variants"} <= table_names(pg_url)

        async def constraint(sessions):
            async with sessions() as s:
                return (await s.execute(text("select count(*) from pg_constraint where conname = 'uq_variants_id_product_id'"))).scalar()
        assert run_repo(pg_engine_factory, constraint) == 0
    finally:
        command.upgrade(config, "head")
    assert "catalog_attributes" in table_names(pg_url)
