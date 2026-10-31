"""Upgrade path of an existing database: main's chain ends at 0009, this branch adds 0010-0015.

The database is brought down to 0009 with the real downgrades, filled with representative rows written by the 0009-era
code paths, then upgraded to head. Nothing here touches a shared database (Testcontainers only). It proves:
one head, a linear chain, no table-name collisions with main's tables, additive upgrade, rows and vectors preserved,
and that the catalogue and the canonical embedding search keep working on the upgraded database."""
import uuid

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text

from configuration.config import settings
from models.relational_model import EMBEDDING_DIMENSIONS
from repositories import products as catalogue
from repositories.hybrid import QueryEmbedding, hybrid_search
from search import embedding_service as svc
from search.providers import FakeEmbeddingProvider
from tests.integration.api_support import ApiEnv
from tests.integration.conftest import alembic_config
from tests.integration.repo_helpers import product_input, run_repo, tx

INDEX = "idx-upgrade"
FAKE = FakeEmbeddingProvider(EMBEDDING_DIMENSIONS)
MAIN_TABLES_0009 = {"product_embeddings", "variant_embeddings", "catalog_attributes", "enrichment_suggestions", "products", "variants",
                    "audit_log", "staged_products", "ingestion_jobs"}
NEW_TABLES = {"admin_accounts", "admin_sessions", "enquiries", "semantic_embeddings", "semantic_embedding_jobs", "action_executions",
              "memory_consents", "memory_items", "customer_sessions"}


def tables(env):
    return {r[0] for r in env.sql("select table_name from information_schema.tables where table_schema = 'public'")}


@pytest.fixture
def at_0009(pg_url, migrated_url, pg_engine_factory, monkeypatch):
    config = alembic_config(pg_url)
    command.downgrade(config, "0009")           # the real downgrades 0015..0010; also proves they run
    monkeypatch.setattr(settings, "embedding_index_version", INDEX)
    yield config, ApiEnv(pg_url, monkeypatch)
    monkeypatch.undo()
    command.upgrade(config, "head")


def test_graph_has_one_head_and_a_linear_chain(pg_url):
    script = ScriptDirectory.from_config(alembic_config(pg_url))
    assert script.get_heads() == ["0015"]
    revisions = list(script.walk_revisions("base", "heads"))[::-1]
    assert [r.revision for r in revisions] == [f"{i:04d}" for i in range(1, 16)]
    assert all(r.down_revision == f"{i:04d}" for i, r in enumerate(revisions[1:], 1))     # nothing branches or skips
    assert len({r.revision for r in revisions}) == 15                                    # no duplicated revision ids


def test_downgrade_to_0009_leaves_exactly_mains_schema(at_0009):
    _, env = at_0009
    present = tables(env)
    assert not (present & NEW_TABLES) and MAIN_TABLES_0009 <= present
    assert "outcome" not in {r[0] for r in env.sql("select column_name from information_schema.columns where table_name = 'audit_log'")}


def test_upgrade_keeps_rows_vectors_and_serving(at_0009):
    config, env = at_0009
    audit_id = env.sql("insert into audit_log (actor_type, action, target) values ('admin', 'product.update', 'p1') returning id")[0][0]

    async def seed(sessions):
        async with tx(sessions) as s:
            p = await catalogue.create_product(s, product_input("upgrade-shawl", name="Upgrade Shawl", status="active"))
            owner = p.id
        async with tx(sessions) as s:
            row, _ = await svc.ensure_pending(s, "product", owner, FAKE, index_version=INDEX, max_attempts=3)
        assert (await svc.process(sessions, FAKE, "product", row.id, lease_seconds=60, backoff_seconds=0))["status"] == "succeeded"
        return owner

    owner = env.run(seed)
    vector_before = env.sql("select embedding::text from product_embeddings where product_id = :p", p=owner)[0][0]
    counts = {t: env.sql(f"select count(*) from {t}")[0][0] for t in ("products", "variants", "product_embeddings", "audit_log")}
    before = tables(env)

    command.upgrade(config, "head")

    assert tables(env) - before == NEW_TABLES                                         # additive: only new tables appear
    assert {t: env.sql(f"select count(*) from {t}")[0][0] for t in counts} == counts  # no row lost
    assert env.sql("select embedding::text from product_embeddings where product_id = :p", p=owner)[0][0] == vector_before
    assert env.sql("select outcome, detail from audit_log where id = :i", i=audit_id) == [("success", None)]   # 0010 backfills its default
    assert env.sql("select count(*) from semantic_embeddings")[0][0] == 0             # legacy tables start (and stay) empty
    with pytest.raises(Exception):                                                    # 0010's append-only guard now protects old rows too
        env.sql("delete from audit_log where id = :i", i=audit_id)

    async def serve(sessions):
        async with sessions() as s:
            source = await svc.load_source(s, "product", owner)
            q = QueryEmbedding(FAKE, (await FAKE.embed([source.representation.text]))[0])
            page = await hybrid_search(s, q="upgrade", limit=10, embedding=q)
            listing = await catalogue.list_products(s, public=True, limit=10)
        return page, listing

    page, listing = env.run(serve)
    assert page.mode == "hybrid" and [p.id for p in page.items] == [owner] == [p.id for p in listing.items]


def test_foreign_keys_and_checks_of_new_tables_work_after_upgrade(at_0009):
    config, env = at_0009
    command.upgrade(config, "head")
    bogus = uuid.uuid4()
    with pytest.raises(Exception):   # semantic_embedding_jobs -> products foreign key is enforced
        env.sql("insert into semantic_embedding_jobs (product_id, provider, model, representation_version, status, max_attempts) "
                "values (:p, 'fake', 'm', 'v', 'queued', 3)", p=bogus)


def test_legacy_numbering_is_detected_read_only(pg_url, migrated_url, monkeypatch):
    """A database stamped 0009 that already holds admin_accounts is the old integration numbering: refuse, never stamp."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("stamp_check", Path(__file__).resolve().parents[2] / "scripts" / "check_migration_stamp.py")
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    env = ApiEnv(pg_url, monkeypatch)
    import asyncio
    assert asyncio.run(check.inspect(pg_url)) == ("0015", None)
    env.sql("update alembic_version set version_num = '0009'")
    try:
        version, why = asyncio.run(check.inspect(pg_url))
        assert version == "0009" and "admin_accounts" in why
    finally:
        env.sql("update alembic_version set version_num = '0015'")
