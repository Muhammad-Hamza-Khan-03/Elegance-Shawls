"""S3: the PostgreSQL catalogue / ingestion schema, against a real PostgreSQL (pgvector) container.

Schema only: no routes and no ingestion code use these tables yet.
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from database.pg import make_engine
from tests.integration.conftest import alembic_config
from tests.integration.test_postgres_schema import run

NOW = datetime.now(timezone.utc)
JSON_COLUMNS = {"product", "source_attributes", "result"}
RELATIONAL = {"customers", "customer_identities", "conversations", "messages", "tool_calls", "events", "audit_log"}
MIGRATION_STEPS = [
    ("0001", RELATIONAL),
    ("0002", {"outbox"}),
    ("0003", {"products", "variants"}),
    ("0004", {"ingestion_jobs", "staged_products", "staged_product_audit"}),
    ("0005", set()),
    ("0006", set()),
    ("0007", {"admin_accounts", "admin_sessions"}),
]


# ---- helpers ---------------------------------------------------------------------------------
async def insert(conn, table, **values):
    columns = ", ".join(values)
    params = ", ".join(f"CAST(:{k} AS jsonb)" if k in JSON_COLUMNS else f":{k}" for k in values)
    prepared = {k: json.dumps(v) if k in JSON_COLUMNS else v for k, v in values.items()}
    return (await conn.execute(text(f"insert into {table} ({columns}) values ({params}) returning id"), prepared)).scalar()


async def scalar(conn, sql, **params):
    return (await conn.execute(text(sql), params)).scalar()


async def row(conn, sql, **params):
    return tuple((await conn.execute(text(sql), params)).one())


def product(**over):
    return {"slug": "classic-pashmina", "name": "Classic Pashmina", "cover_image_url": "https://img.example/c.jpg",
            "price": 4500, **over}


def variant(product_id, **over):
    return {"product_id": product_id, "position": 0, "name": "Burgundy", "image_url": "https://img.example/b.jpg",
            "price": 4500, "stock": 4, **over}


def job(**over):
    return {"source_id": "primary", "path": "/products/classic", "idempotency_key": "primary:/products/classic", **over}


def staged(**over):
    return {"source_id": "primary", "source_name": "Primary", "source_url": "https://source.example/p/1",
            "source_content_hash": "h1", "dedupe_key": "url:https://source.example/p/1",
            "fetched_at": NOW, "normalized_at": NOW,
            "product": {"name": "Classic", "slug": "classic", "variants": [{"name": "Burgundy"}]}, **over}


def rejects(factory, work, error=IntegrityError):
    with pytest.raises(error):
        run(factory, work)


def table_names(url):
    async def go():
        engine = make_engine(url)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text("select tablename from pg_tables where schemaname='public'"))
                return {r[0] for r in result} - {"alembic_version"}
        finally:
            await engine.dispose()

    return asyncio.run(go())


def column_type(url, table, column):
    async def go():
        engine = make_engine(url)
        try:
            async with engine.connect() as conn:
                return await scalar(conn, "select data_type from information_schema.columns "
                                          "where table_name=:t and column_name=:c", t=table, c=column)
        finally:
            await engine.dispose()

    return asyncio.run(go())


# ---- migrations ------------------------------------------------------------------------------
def test_each_migration_applies_and_reverses_one_step_at_a_time(pg_url, migrated_url, pg_engine_factory):   # fixture empties the 0007 tables
    config = alembic_config(pg_url)
    try:
        command.downgrade(config, "base")
        assert table_names(pg_url) == set()                      # fully reversible down to nothing
        seen: set[str] = set()
        for revision, new in MIGRATION_STEPS:
            command.upgrade(config, revision)
            seen |= new
            assert seen <= table_names(pg_url)
        previous = ["base"] + [r for r, _ in MIGRATION_STEPS][:-1]
        for (revision, new), before in reversed(list(zip(MIGRATION_STEPS, previous))):
            command.downgrade(config, before)
            assert not (new & table_names(pg_url))                # exactly that step is undone
    finally:
        command.upgrade(config, "head")                           # later tests share this database
    assert {"products", "variants", "ingestion_jobs", "staged_products", "staged_product_audit", "outbox"} <= table_names(pg_url)


def test_empty_database_bootstraps_to_an_empty_usable_catalogue(pg_url, migrated_url, pg_engine_factory):
    config = alembic_config(pg_url)
    try:
        command.downgrade(config, "base")
        command.upgrade(config, "head")                           # re-upgrade from nothing
    finally:
        command.upgrade(config, "head")

    async def work(conn):
        counts = {t: await scalar(conn, f"select count(*) from {t}")
                  for t in ("products", "variants", "ingestion_jobs", "staged_products", "staged_product_audit", "outbox")}
        extension = await scalar(conn, "select extname from pg_extension where extname='vector'")
        return counts, extension

    counts, extension = run(pg_engine_factory, work)
    assert counts == dict.fromkeys(counts, 0)                     # no seed data: nothing needs migrating
    assert extension == "vector"

    async def first_product(conn):                                # and it accepts the first product immediately
        return await insert(conn, "products", **product())

    assert isinstance(run(pg_engine_factory, first_product), uuid.UUID)


def test_triggers_and_functions_are_removed_by_downgrade(pg_url, migrated_url):
    config = alembic_config(pg_url)

    def present():
        async def go():
            engine = make_engine(pg_url)
            try:
                async with engine.connect() as conn:
                    return await scalar(conn, "select count(*) from pg_proc where proname='staged_product_audit_append_only'")
            finally:
                await engine.dispose()

        return asyncio.run(go())

    try:
        assert present() == 1
        command.downgrade(config, "0003")
        assert present() == 0
    finally:
        command.upgrade(config, "head")


def test_outbox_identifier_is_char24_before_0005_and_uuid_after(pg_url, migrated_url):
    config = alembic_config(pg_url)
    try:
        assert column_type(pg_url, "outbox", "aggregate_id") == "uuid"
        command.downgrade(config, "0004")
        assert column_type(pg_url, "outbox", "aggregate_id") == "character"
    finally:
        command.upgrade(config, "head")
    assert column_type(pg_url, "outbox", "aggregate_id") == "uuid"


def test_outbox_migration_refuses_to_rewrite_existing_rows(pg_url, migrated_url, pg_engine_factory):
    """An outbox that already holds rows is never silently converted in either direction."""
    config = alembic_config(pg_url)
    row_id = str(uuid.uuid4())

    async def add(conn):
        await conn.execute(text("insert into outbox(aggregate, aggregate_id, revision, event_type) "
                                "values ('product', :i, 1, 'created')"), {"i": row_id})

    async def clear(conn):
        await conn.execute(text("delete from outbox"))

    run(pg_engine_factory, add)
    try:
        with pytest.raises(Exception):                            # uuid text (36 chars) does not fit CHAR(24)
            command.downgrade(config, "0004")
        assert column_type(pg_url, "outbox", "aggregate_id") == "uuid"   # transactional DDL: nothing changed
    finally:
        run(pg_engine_factory, clear)
        command.upgrade(config, "head")


# ---- UUID behaviour --------------------------------------------------------------------------
def test_identifiers_are_server_generated_version4_uuids(pg_engine_factory):
    async def work(conn):
        ids = [await insert(conn, "products", **product(slug=f"p-{i}")) for i in range(3)]
        return ids, await scalar(conn, "select pg_typeof(id)::text from products limit 1")

    ids, type_name = run(pg_engine_factory, work)
    assert type_name == "uuid" and len(set(ids)) == 3
    assert all(isinstance(i, uuid.UUID) and i.version == 4 for i in ids)


def test_a_legacy_24_hex_identifier_is_not_a_valid_key(pg_engine_factory):
    async def work(conn):
        await scalar(conn, "select count(*) from products where id = :i", i="507f1f77bcf86cd799439011")

    rejects(pg_engine_factory, work, DBAPIError)


# ---- products --------------------------------------------------------------------------------
def test_product_defaults_are_a_private_draft(pg_engine_factory):
    async def work(conn):
        pid = await insert(conn, "products", **product())
        return await row(conn, "select status, is_active, revision, currency, images, category, "
                               "created_at, updated_at from products where id=:i", i=pid)

    status, active, revision, currency, images, category, created, updated = run(pg_engine_factory, work)
    assert (status, active, revision, currency, images, category) == ("draft", False, 1, "PKR", [], "shawls")
    assert created.tzinfo is not None and updated.tzinfo is not None


def test_is_active_is_derived_from_status_and_cannot_be_written(pg_engine_factory):
    async def work(conn):
        pid = await insert(conn, "products", **product())
        flags = []
        for status in ("active", "draft", "out_of_stock", "archived"):
            await conn.execute(text("update products set status=:s where id=:i"), {"s": status, "i": pid})
            flags.append(await scalar(conn, "select is_active from products where id=:i", i=pid))
        return flags

    assert run(pg_engine_factory, work) == [True, False, False, False]

    async def write(conn):
        await conn.execute(text("insert into products(slug, name, cover_image_url, price, is_active) "
                                "values ('x','X','u',1,true)"))

    rejects(pg_engine_factory, write, DBAPIError)


@pytest.mark.parametrize("over", [
    {"slug": "Has Space"}, {"slug": "UPPER"}, {"slug": "-leading"}, {"slug": "double--hyphen"}, {"slug": "a" * 181},
    {"name": ""}, {"name": "n" * 161},
    {"category": "hats"}, {"status": "published"},
    {"images": [f"https://img/{i}.jpg" for i in range(13)]},
    {"price": -1}, {"currency": "pkr"}, {"revision": 0},
    {"main_description": "d" * 5001}, {"material": "m" * 201}, {"weight": "w" * 101}, {"item_number": "i" * 101},
])
def test_product_constraints_reject_invalid_rows(pg_engine_factory, over):
    async def work(conn):
        await insert(conn, "products", **product(**over))

    rejects(pg_engine_factory, work)


def test_product_boundaries_are_accepted(pg_engine_factory):
    async def work(conn):
        await insert(conn, "products", **product(slug="a" * 180, name="n" * 160, images=["u"] * 12,
                                                 main_description="d" * 5000, item_number="i" * 100, price=0))

    run(pg_engine_factory, work)


def test_product_slug_is_unique(pg_engine_factory):
    async def work(conn):
        await insert(conn, "products", **product())
        await insert(conn, "products", **product(name="Another"))

    rejects(pg_engine_factory, work)


def test_item_number_is_not_unique(pg_engine_factory):
    async def work(conn):
        await insert(conn, "products", **product(slug="one", item_number="ES-1"))
        await insert(conn, "products", **product(slug="two", item_number="ES-1"))

    run(pg_engine_factory, work)


# ---- variants --------------------------------------------------------------------------------
def test_variants_belong_to_a_product_and_are_deleted_with_it(pg_engine_factory):
    async def work(conn):
        pid = await insert(conn, "products", **product())
        for position, name in enumerate(("Burgundy", "Black")):
            await insert(conn, "variants", **variant(pid, position=position, name=name))
        names = [r[0] for r in await conn.execute(text("select name from variants where product_id=:p order by position"), {"p": pid})]
        await conn.execute(text("delete from products where id=:p"), {"p": pid})
        return names, await scalar(conn, "select count(*) from variants")

    assert run(pg_engine_factory, work) == (["Burgundy", "Black"], 0)


def test_variant_needs_an_existing_product(pg_engine_factory):
    async def work(conn):
        await insert(conn, "variants", **variant(uuid.uuid4()))

    rejects(pg_engine_factory, work)


def test_stock_status_is_derived_from_stock(pg_engine_factory):
    async def work(conn):
        pid = await insert(conn, "products", **product())
        vid = await insert(conn, "variants", **variant(pid, stock=3))
        states = [await scalar(conn, "select stock_status from variants where id=:i", i=vid)]
        await conn.execute(text("update variants set stock=0 where id=:i"), {"i": vid})
        states.append(await scalar(conn, "select stock_status from variants where id=:i", i=vid))
        return states

    assert run(pg_engine_factory, work) == ["In stock", "Out of stock"]


@pytest.mark.parametrize("over", [{"stock": -1}, {"price": -1}, {"position": -1}, {"color": ""}, {"name": ""}, {"currency": "usd"}])
def test_variant_constraints_reject_invalid_rows(pg_engine_factory, over):
    async def work(conn):
        pid = await insert(conn, "products", **product())
        await insert(conn, "variants", **variant(pid, **over))

    rejects(pg_engine_factory, work)


def test_variant_defaults(pg_engine_factory):
    async def work(conn):
        pid = await insert(conn, "products", **product())
        vid = await insert(conn, "variants", product_id=pid, position=0, name="V", image_url="u", price=1)
        return await row(conn, "select size, currency, stock, is_active, color from variants where id=:i", i=vid)

    assert run(pg_engine_factory, work) == ("Free Size", "PKR", 0, True, None)


def test_variant_positions_are_unique_per_product_but_can_be_swapped_in_one_transaction(pg_engine_factory):
    async def swap(conn):
        pid = await insert(conn, "products", **product())
        a = await insert(conn, "variants", **variant(pid, position=0, name="A"))
        b = await insert(conn, "variants", **variant(pid, position=1, name="B"))
        await conn.execute(text("update variants set position = 1 where id=:i"), {"i": a})   # transiently duplicates b
        await conn.execute(text("update variants set position = 0 where id=:i"), {"i": b})
        return [r[0] for r in await conn.execute(text("select name from variants order by position"))]

    assert run(pg_engine_factory, swap) == ["B", "A"]

    async def duplicate(conn):
        pid = await insert(conn, "products", **product(slug="dup"))
        await insert(conn, "variants", **variant(pid, position=0))
        await insert(conn, "variants", **variant(pid, position=0, name="Other"))

    rejects(pg_engine_factory, duplicate)

    async def other_products(conn):                               # the same position on another product is fine
        for slug in ("one", "two"):
            await insert(conn, "variants", **variant(await insert(conn, "products", **product(slug=slug)), position=0))

    run(pg_engine_factory, other_products)


# ---- indexes ---------------------------------------------------------------------------------
def _plan(factory, sql):
    async def work(conn):
        await conn.execute(text("set local enable_seqscan = off"))
        return "\n".join(r[0] for r in await conn.execute(text("explain " + sql)))

    return run(factory, work)


def test_public_feed_query_uses_the_partial_cursor_index(pg_engine_factory):
    async def seed(conn):
        for i in range(5):
            await insert(conn, "products", **product(slug=f"p-{i}", status="active" if i % 2 == 0 else "draft"))

    run(pg_engine_factory, seed)
    plan = _plan(pg_engine_factory, "select id from products where status='active' "
                                    "and (created_at, id) < (now(), gen_random_uuid()) order by created_at desc, id desc limit 20")
    assert "ix_products_public_feed" in plan


def test_admin_list_uses_the_all_states_index(pg_engine_factory):
    assert "ix_products_created_at_id" in _plan(pg_engine_factory, "select id from products order by created_at desc, id desc limit 20")


def test_index_definitions_are_partial_where_intended(pg_engine_factory):
    async def work(conn):
        return dict((await conn.execute(text("select indexname, indexdef from pg_indexes where schemaname='public'"))).all())

    defs = run(pg_engine_factory, work)
    assert "WHERE (status = 'active'::text)" in defs["ix_products_public_feed"]
    assert "WHERE (item_number IS NOT NULL)" in defs["ix_products_item_number"]
    assert "NOT cancel_requested" in defs["ix_ingestion_jobs_claimable"] and "queued" in defs["ix_ingestion_jobs_claimable"]
    assert "WHERE (status = 'running'::text)" in defs["ix_ingestion_jobs_running_lease"]
    assert "WHERE (product_id IS NOT NULL)" in defs["ix_staged_products_product_id"]
    assert "created_at DESC" in defs["ix_staged_products_review_feed"]
    assert "(staged_product_id, seq)" in defs["ix_staged_product_audit_staged_product_id_seq"]
    assert "UNIQUE" in defs["uq_variants_product_id_position"] and "UNIQUE" in defs["uq_staged_products_source_id_dedupe_key"]


# ---- ingestion jobs --------------------------------------------------------------------------
def test_job_defaults_are_queued_and_claimable(pg_engine_factory):
    async def work(conn):
        jid = await insert(conn, "ingestion_jobs", **job())
        return await row(conn, "select status, attempts, max_attempts, cancel_requested, lease_owner, "
                               "lease_expires_at, result, available_at <= now() from ingestion_jobs where id=:i", i=jid)

    assert run(pg_engine_factory, work) == ("queued", 0, 3, False, None, None, None, True)


@pytest.mark.parametrize("over", [
    {"status": "paused"}, {"path": ""}, {"path": "/" + "p" * 220}, {"attempts": -1}, {"max_attempts": 0},
    {"attempts": 4, "max_attempts": 3},
    {"status": "running"},                                                       # running needs an owner and a lease
    {"status": "running", "lease_owner": "w1"},
    {"status": "running", "lease_expires_at": NOW},
])
def test_job_constraints_reject_invalid_rows(pg_engine_factory, over):
    async def work(conn):
        await insert(conn, "ingestion_jobs", **job(**over))

    rejects(pg_engine_factory, work)


def test_running_job_with_a_lease_is_accepted_and_idempotency_key_is_unique(pg_engine_factory):
    async def ok(conn):
        await insert(conn, "ingestion_jobs", **job(status="running", lease_owner="w1", lease_expires_at=NOW + timedelta(minutes=2),
                                                   attempts=1, heartbeat_at=NOW, started_at=NOW))

    run(pg_engine_factory, ok)

    async def duplicate(conn):
        await insert(conn, "ingestion_jobs", **job())
        await insert(conn, "ingestion_jobs", **job(path="/other"))

    rejects(pg_engine_factory, duplicate)


def test_claim_query_uses_the_partial_index_and_skips_cancelled_and_future_jobs(pg_engine_factory):
    async def seed(conn):
        await insert(conn, "ingestion_jobs", **job(idempotency_key="due"))
        await insert(conn, "ingestion_jobs", **job(idempotency_key="future", available_at=NOW + timedelta(hours=1)))
        await insert(conn, "ingestion_jobs", **job(idempotency_key="cancelled", cancel_requested=True))
        await insert(conn, "ingestion_jobs", **job(idempotency_key="retry", status="retrying", attempts=1))
        await insert(conn, "ingestion_jobs", **job(idempotency_key="done", status="succeeded", attempts=1))

    run(pg_engine_factory, seed)
    claim = ("select idempotency_key from ingestion_jobs where status in ('queued','retrying') "
             "and not cancel_requested and available_at <= now() order by available_at")

    async def claimable(conn):
        return sorted(r[0] for r in await conn.execute(text(claim)))

    assert run(pg_engine_factory, claimable) == ["due", "retry"]
    assert "ix_ingestion_jobs_claimable" in _plan(pg_engine_factory, claim)


def test_two_workers_cannot_claim_the_same_job(pg_engine_factory):
    """FOR UPDATE SKIP LOCKED hands each concurrent claimer a different row."""
    async def seed(conn):
        await insert(conn, "ingestion_jobs", **job(idempotency_key="one"))
        await insert(conn, "ingestion_jobs", **job(idempotency_key="two"))

    run(pg_engine_factory, seed)
    sql = text("select idempotency_key from ingestion_jobs where status='queued' order by available_at, id "
               "for update skip locked limit 1")

    async def race():
        engine = pg_engine_factory()
        try:
            async with engine.connect() as first, engine.connect() as second, engine.connect() as third:
                a = (await first.execute(sql)).scalar()       # first worker holds its row lock...
                b = (await second.execute(sql)).scalar()      # ...so the second gets the other one...
                c = (await third.execute(sql)).scalar()       # ...and the third finds nothing.
                return a, b, c
        finally:
            await engine.dispose()

    a, b, c = asyncio.run(race())
    assert {a, b} == {"one", "two"} and c is None


# ---- staged products -------------------------------------------------------------------------
def test_staged_product_defaults_and_json_round_trip(pg_engine_factory):
    async def work(conn):
        sid = await insert(conn, "staged_products", **staged(source_attributes={"origin": "Kashmir"},
                                                             missing_fields=["price", "stock"], source_price=29.5,
                                                             source_currency="USD"))
        return await row(conn, "select status, stock_known, product->>'slug', product->'variants'->0->>'name', "
                               "source_attributes->>'origin', missing_fields, source_price, source_currency, "
                               "product_id, approved_price from staged_products where id=:i", i=sid)

    assert run(pg_engine_factory, work) == ("pending_review", False, "classic", "Burgundy", "Kashmir",
                                            ["price", "stock"], 29.5, "USD", None, None)


@pytest.mark.parametrize("over", [
    {"status": "live"}, {"source_price": -1},
    {"status": "rejected"},                                                      # a rejection needs a reason...
    {"status": "rejected", "rejection_reason": "no"},                            # ...of at least 3 characters
    {"status": "approved"}, {"status": "published"}, {"status": "unpublished"},  # these need a product and a price
    {"approved_price": -1, "approved_stock": 0}, {"approved_price": 1, "approved_stock": -1},
])
def test_staged_product_constraints_reject_invalid_rows(pg_engine_factory, over):
    async def work(conn):
        await insert(conn, "staged_products", **staged(**over))

    rejects(pg_engine_factory, work)


def test_rejected_with_reason_and_archived_without_a_product_are_valid(pg_engine_factory):
    async def work(conn):
        await insert(conn, "staged_products", **staged(status="rejected", rejection_reason="Wrong category", dedupe_key="a"))
        await insert(conn, "staged_products", **staged(status="archived", dedupe_key="b"))

    run(pg_engine_factory, work)


def test_staged_identity_is_unique_per_source(pg_engine_factory):
    async def duplicate(conn):
        await insert(conn, "staged_products", **staged())
        await insert(conn, "staged_products", **staged(source_content_hash="h2"))

    rejects(pg_engine_factory, duplicate)

    async def other_source(conn):                                                # same key, different source: fine
        await insert(conn, "staged_products", **staged())
        await insert(conn, "staged_products", **staged(source_id="second"))

    run(pg_engine_factory, other_source)


def test_staged_product_links_to_its_job_and_survives_job_deletion(pg_engine_factory):
    async def work(conn):
        jid = await insert(conn, "ingestion_jobs", **job())
        sid = await insert(conn, "staged_products", **staged(ingestion_job_id=jid))
        linked = await scalar(conn, "select ingestion_job_id from staged_products where id=:i", i=sid)
        await conn.execute(text("delete from ingestion_jobs where id=:j"), {"j": jid})
        return linked == jid, await scalar(conn, "select ingestion_job_id from staged_products where id=:i", i=sid)

    assert run(pg_engine_factory, work) == (True, None)


def test_unknown_job_or_product_links_are_rejected(pg_engine_factory):
    async def bad_job(conn):
        await insert(conn, "staged_products", **staged(ingestion_job_id=uuid.uuid4()))

    async def bad_product(conn):
        await insert(conn, "staged_products", **staged(product_id=uuid.uuid4()))

    rejects(pg_engine_factory, bad_job)
    rejects(pg_engine_factory, bad_product)


def test_a_product_that_came_from_a_review_cannot_be_hard_deleted(pg_engine_factory):
    async def work(conn):
        pid = await insert(conn, "products", **product())
        await insert(conn, "staged_products", **staged(status="approved", product_id=pid, approved_price=4500,
                                                       approved_stock=2, stock_known=True))
        await conn.execute(text("delete from products where id=:p"), {"p": pid})

    rejects(pg_engine_factory, work)


def test_target_flow_stage_approve_then_manual_publish(pg_engine_factory):
    """source -> staged (pending_review) -> approve (draft product) -> manual publish, at schema level."""
    async def work(conn):
        jid = await insert(conn, "ingestion_jobs", **job())
        sid = await insert(conn, "staged_products", **staged(ingestion_job_id=jid, missing_fields=["price", "stock"]))
        await insert(conn, "staged_product_audit", staged_product_id=sid, action="staged", to_status="pending_review", actor="ingestion")

        # approve: one transaction creates the DRAFT product + variants and records the human-entered price
        pid = await insert(conn, "products", **product(status="draft", price=4500))
        await insert(conn, "variants", **variant(pid, stock=2))
        await conn.execute(text("update staged_products set status='approved', product_id=:p, approved_price=4500, "
                                "approved_stock=2, stock_known=true where id=:s"), {"p": pid, "s": sid})
        await insert(conn, "staged_product_audit", staged_product_id=sid, action="approve",
                     from_status="pending_review", to_status="approved")
        public_before = await scalar(conn, "select count(*) from products where status='active' and is_active")

        # publish is a separate, manual step
        await conn.execute(text("update products set status='active' where id=:p"), {"p": pid})
        await conn.execute(text("update staged_products set status='published' where id=:s"), {"s": sid})
        await insert(conn, "staged_product_audit", staged_product_id=sid, action="publish",
                     from_status="approved", to_status="published")
        public_after = await scalar(conn, "select count(*) from products where status='active' and is_active")
        trail = [r[0] for r in await conn.execute(text("select action from staged_product_audit order by seq"))]
        return public_before, public_after, trail

    assert run(pg_engine_factory, work) == (0, 1, ["staged", "approve", "publish"])   # approval alone publishes nothing


# ---- audit: append-only ----------------------------------------------------------------------
async def _staged_with_one_audit_row(conn):
    sid = await insert(conn, "staged_products", **staged())
    aid = await insert(conn, "staged_product_audit", staged_product_id=sid, action="staged", to_status="pending_review")
    return sid, aid


def test_audit_defaults_and_ordering(pg_engine_factory):
    async def work(conn):
        sid, aid = await _staged_with_one_audit_row(conn)
        await insert(conn, "staged_product_audit", staged_product_id=sid, action="reject", from_status="pending_review",
                     to_status="rejected", note="duplicate")
        rows = (await conn.execute(text("select action, actor, at is not null from staged_product_audit "
                                        "where staged_product_id=:s order by seq"), {"s": sid})).all()
        return [tuple(r) for r in rows]

    assert run(pg_engine_factory, work) == [("staged", "admin", True), ("reject", "admin", True)]


def test_audit_rows_cannot_be_updated(pg_engine_factory):
    async def work(conn):
        _, aid = await _staged_with_one_audit_row(conn)
        await conn.execute(text("update staged_product_audit set note='tampered' where id=:i"), {"i": aid})

    with pytest.raises(IntegrityError, match="append-only"):
        run(pg_engine_factory, work)


def test_audit_rows_cannot_be_deleted(pg_engine_factory):
    async def work(conn):
        _, aid = await _staged_with_one_audit_row(conn)
        await conn.execute(text("delete from staged_product_audit where id=:i"), {"i": aid})

    with pytest.raises(IntegrityError, match="append-only"):
        run(pg_engine_factory, work)


def test_deleting_a_staged_product_with_a_trail_is_refused(pg_engine_factory):
    async def work(conn):
        sid, _ = await _staged_with_one_audit_row(conn)
        await conn.execute(text("delete from staged_products where id=:s"), {"s": sid})

    rejects(pg_engine_factory, work)


def test_audit_order_is_strict_even_inside_one_transaction(pg_engine_factory):
    async def work(conn):
        sid = await insert(conn, "staged_products", **staged())
        for n in range(20):                                   # one transaction: now() would be identical for all rows
            await insert(conn, "staged_product_audit", staged_product_id=sid, action=f"step-{n:02d}")
        actions = [r[0] for r in await conn.execute(text("select action from staged_product_audit order by seq"))]
        distinct_now = await scalar(conn, "select count(distinct at) from staged_product_audit")
        return actions == [f"step-{n:02d}" for n in range(20)], distinct_now > 1

    assert run(pg_engine_factory, work) == (True, True)      # seq orders them; `at` is real wall-clock time


@pytest.mark.parametrize("over", [{"from_status": "live"}, {"to_status": "live"}, {"action": ""}])
def test_audit_constraints_reject_invalid_rows(pg_engine_factory, over):
    async def work(conn):
        sid = await insert(conn, "staged_products", **staged())
        await insert(conn, "staged_product_audit", **{"staged_product_id": sid, "action": "x", **over})

    rejects(pg_engine_factory, work)


def test_audit_needs_an_existing_staged_product(pg_engine_factory):
    async def work(conn):
        await insert(conn, "staged_product_audit", staged_product_id=uuid.uuid4(), action="staged")

    rejects(pg_engine_factory, work)


# ---- the SQLAlchemy models map the same tables ------------------------------------------------
def test_models_round_trip_through_the_orm(pg_engine_factory):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.relational_model import IngestionJob, Product, StagedProduct, StagedProductAudit, Variant

    async def work():
        engine = pg_engine_factory()
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                prod = Product(slug="orm-shawl", name="ORM Shawl", cover_image_url="u", price=100, status="active",
                               images=["a", "b"])
                session.add(prod)
                await session.flush()
                session.add(Variant(product_id=prod.id, position=0, name="V", image_url="u", price=100, stock=5))
                job_row = IngestionJob(source_id="s", path="/p", idempotency_key="k")
                session.add(job_row)
                await session.flush()
                stage = StagedProduct(source_id="s", source_name="S", source_url="https://s/p", source_content_hash="h",
                                      dedupe_key="url:https://s/p", fetched_at=NOW, normalized_at=NOW,
                                      ingestion_job_id=job_row.id, product={"name": "x"})
                session.add(stage)
                await session.flush()
                session.add(StagedProductAudit(staged_product_id=stage.id, action="staged", to_status="pending_review"))
                await session.commit()
            async with AsyncSession(engine) as session:
                loaded = (await session.execute(select(Product).where(Product.slug == "orm-shawl"))).scalar_one()
                variants = (await session.execute(select(Variant).where(Variant.product_id == loaded.id))).scalars().all()
                staged_row = (await session.execute(select(StagedProduct))).scalar_one()
                return (loaded.is_active, loaded.revision, loaded.images, [(v.stock_status, v.size) for v in variants],
                        staged_row.status, staged_row.stock_known, staged_row.product, isinstance(loaded.id, uuid.UUID))
        finally:
            await engine.dispose()

    assert asyncio.run(work()) == (True, 1, ["a", "b"], [("In stock", "Free Size")], "pending_review", False, {"name": "x"}, True)


# ---- model / migration agreement beyond what Alembic compares ----------------------------------
# Alembic's compare ignores CHECK constraints, computed columns and index expressions, so check them directly.
def _model_tables():
    from models.relational_model import Base

    return Base.metadata.tables


def test_constraint_names_in_models_and_database_are_identical(pg_engine_factory):
    """Primary, unique, foreign-key and CHECK constraints: the DDL the models render vs what the migrations built."""
    import re

    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    async def work(conn):
        return {tuple(r) for r in await conn.execute(text(
            "select conrelid::regclass::text, conname from pg_constraint "
            "where connamespace='public'::regnamespace and contype in ('p','u','f','c') and conrelid::regclass::text <> 'alembic_version'"))}

    expected = set()
    for table in _model_tables().values():
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        expected |= {(table.name, name) for name in re.findall(r"CONSTRAINT (\w+)", ddl)}
    actual = run(pg_engine_factory, work)
    assert expected == actual, (sorted(expected - actual), sorted(actual - expected))


def test_index_names_in_models_and_database_are_identical(pg_engine_factory):
    async def work(conn):
        return {tuple(r) for r in await conn.execute(text(
            "select tablename, indexname from pg_indexes where schemaname='public' "
            "and indexname not like 'pk\\_%' and indexname not like 'uq\\_%' and tablename <> 'alembic_version'"))}

    in_models = {(table.name, i.name) for table in _model_tables().values() for i in table.indexes}
    assert in_models == run(pg_engine_factory, work)


def test_computed_columns_and_column_defaults_agree(pg_engine_factory):
    async def work(conn):
        rows = await conn.execute(text(
            "select table_name, column_name, is_generated, generation_expression from information_schema.columns "
            "where table_schema='public' and is_generated='ALWAYS'"))
        return {(r[0], r[1]) for r in rows}

    in_models = {(t.name, c.name) for t in _model_tables().values() for c in t.columns if c.computed is not None}
    assert in_models == {("products", "is_active"), ("variants", "stock_status")} == run(pg_engine_factory, work)


def test_every_model_table_has_a_uuid_primary_key_and_matches_not_null(pg_engine_factory):
    async def work(conn):
        types = {(r[0], r[1]): (r[2], r[3]) for r in await conn.execute(text(
            "select table_name, column_name, data_type, is_nullable from information_schema.columns where table_schema='public'"))}
        return types

    db = run(pg_engine_factory, work)
    for table in _model_tables().values():
        assert db[(table.name, "id")][0] == "uuid" and [c.name for c in table.primary_key.columns] == ["id"]
        for column in table.columns:
            assert (db[(table.name, column.name)][1] == "NO") == (not column.nullable), f"{table.name}.{column.name}"
