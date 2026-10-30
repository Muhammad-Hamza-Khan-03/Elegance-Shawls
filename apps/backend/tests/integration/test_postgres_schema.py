import asyncio
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models.relational_model import Base
from tests.integration.conftest import alembic_config

EXPECTED_TABLES = {
    "customers", "customer_identities", "conversations", "messages", "tool_calls", "events", "audit_log", "outbox",
    "products", "variants", "ingestion_jobs", "staged_products", "staged_product_audit",
    "admin_accounts", "admin_sessions",
}
EXPECTED_INDEXES = {
    "ix_events_type_created_at", "ix_events_customer_id_created_at", "ix_events_session_id_created_at",
    "ix_customer_identities_customer_id", "ix_conversations_customer_id_started_at",
    "ix_messages_conversation_id_created_at", "ix_tool_calls_message_id",
    "ix_audit_log_created_at", "ix_audit_log_target_created_at", "ix_outbox_unprocessed",
}


def run(factory, work):
    async def go():
        engine = factory()
        try:
            async with engine.begin() as conn:
                return await work(conn)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def test_migration_is_reversible(pg_url, migrated_url):
    config = alembic_config(pg_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_tables_indexes_and_vector_extension(pg_engine_factory):
    async def work(conn):
        tables = {r[0] for r in await conn.execute(text(
            "select tablename from pg_tables where schemaname='public'"))}
        indexes = {r[0] for r in await conn.execute(text(
            "select indexname from pg_indexes where schemaname='public'"))}
        ext = (await conn.execute(text("select extname from pg_extension where extname='vector'"))).scalar()
        return tables, indexes, ext

    tables, indexes, ext = run(pg_engine_factory, work)
    assert EXPECTED_TABLES <= tables
    assert EXPECTED_INDEXES <= indexes
    assert ext == "vector"


def test_models_match_migrated_schema(pg_engine_factory):
    def diff(sync_conn):
        return compare_metadata(MigrationContext.configure(sync_conn), Base.metadata)

    async def work(conn):
        return await conn.run_sync(diff)

    assert run(pg_engine_factory, work) == []


def test_application_role_is_least_privilege(pg_engine_factory):
    async def work(conn):
        row = (await conn.execute(text(
            "select rolsuper, rolcreatedb, rolcreaterole from pg_roles where rolname = current_user"))).one()
        return tuple(row)

    assert run(pg_engine_factory, work) == (False, False, False)


def _insert_customer(status="anonymous"):
    async def work(conn):
        return (await conn.execute(text("insert into customers(status) values (:s) returning id"), {"s": status})).scalar()

    return work


def test_check_constraints_reject_bad_values(pg_engine_factory):
    with pytest.raises(IntegrityError):
        run(pg_engine_factory, _insert_customer("vip"))

    async def bad_event(conn):
        await conn.execute(text("insert into events(session_id, type) values ('s', 'teleport')"))

    with pytest.raises(IntegrityError):
        run(pg_engine_factory, bad_event)

    async def bad_audit(conn):
        await conn.execute(text("insert into audit_log(actor_type, action) values ('robot', 'x')"))

    with pytest.raises(IntegrityError):
        run(pg_engine_factory, bad_audit)


def test_identity_provider_subject_is_unique(pg_engine_factory):
    async def work(conn):
        cid = (await conn.execute(text("insert into customers default values returning id"))).scalar()
        sql = text("insert into customer_identities(customer_id, provider, subject) values (:c, 'anon', 'abc')")
        await conn.execute(sql, {"c": cid})
        await conn.execute(sql, {"c": cid})

    with pytest.raises(IntegrityError):
        run(pg_engine_factory, work)


def test_foreign_keys_cascade_and_set_null(pg_engine_factory):
    async def work(conn):
        cid = (await conn.execute(text("insert into customers default values returning id"))).scalar()
        conv = (await conn.execute(text(
            "insert into conversations(customer_id) values (:c) returning id"), {"c": cid})).scalar()
        msg = (await conn.execute(text(
            "insert into messages(conversation_id, role, content) values (:c, 'user', 'hi') returning id"),
            {"c": conv})).scalar()
        await conn.execute(text("insert into tool_calls(message_id, tool, status) values (:m, 'search', 'ok')"), {"m": msg})
        await conn.execute(text("insert into events(customer_id, session_id, type) values (:c, 's', 'view')"), {"c": cid})
        await conn.execute(text("delete from customers where id = :c"), {"c": cid})
        counts = {}
        for table in ("conversations", "messages", "tool_calls"):
            counts[table] = (await conn.execute(text(f"select count(*) from {table}"))).scalar()
        events = (await conn.execute(text("select count(*), count(customer_id) from events"))).one()
        return counts, tuple(events)

    counts, events = run(pg_engine_factory, work)
    assert counts == {"conversations": 0, "messages": 0, "tool_calls": 0}
    assert events == (1, 0)  # event kept, customer link cleared


def test_timestamps_are_utc_aware_and_ids_are_uuids(pg_engine_factory):
    async def work(conn):
        row = (await conn.execute(text("insert into customers default values returning id, created_at"))).one()
        tz = (await conn.execute(text("select extract(timezone from created_at) from customers"))).scalar()
        return row, tz

    (cid, created_at), tz = run(pg_engine_factory, work)
    assert isinstance(cid, uuid.UUID)
    assert created_at.tzinfo is not None
    assert tz == 0  # session timezone is UTC


def test_backup_role_reads_but_cannot_write(pg_engine_factory, backup_url):
    from database.pg import make_engine

    async def work():
        engine = make_engine(backup_url)
        try:
            async with engine.begin() as conn:
                assert (await conn.execute(text("select count(*) from customers"))).scalar() == 0
            with pytest.raises(Exception, match="permission denied"):
                async with engine.begin() as conn:
                    await conn.execute(text("insert into customers default values"))
        finally:
            await engine.dispose()

    asyncio.run(work())


def test_events_endpoint_persists_rows_and_retention_purges_old_ones(pg_engine_factory, migrated_url, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession

    import main
    from configuration.config import settings
    from database.pg import get_pg_session, make_engine
    from events.retention import purge_expired_events

    monkeypatch.setattr(settings, "session_signing_key", "integration-signing-key")
    monkeypatch.setattr(settings, "events_rate_limit_per_minute", 1000)
    app = main.create_app()

    async def real_session():
        engine = make_engine(migrated_url)
        try:
            async with AsyncSession(engine) as session:
                yield session
        finally:
            await engine.dispose()

    app.dependency_overrides[get_pg_session] = real_session
    body = {"events": [{"type": "view", "payload": {"slug": "a"}}, {"type": "search", "payload": {"q": "brown"}}]}
    assert TestClient(app).post("/v1/events", json=body).status_code == 202

    async def work(conn):
        rows = (await conn.execute(text("select type, session_id, customer_id from events order by type"))).all()
        await conn.execute(text("insert into events(session_id, type, created_at) values ('old', 'view', :t)"),
                           {"t": datetime.now(timezone.utc) - timedelta(days=30 * 19)})
        return rows

    rows = run(pg_engine_factory, work)
    assert [r[0] for r in rows] == ["search", "view"] and rows[0][1] == rows[1][1] and rows[0][2] is None

    async def purge():
        engine = make_engine(migrated_url)
        async with AsyncSession(engine) as session:
            deleted = await purge_expired_events(session, months=18)
        await engine.dispose()
        return deleted

    assert asyncio.run(purge()) == 1

    async def remaining(conn):
        return (await conn.execute(text("select count(*) from events"))).scalar()

    assert run(pg_engine_factory, remaining) == 2


PRODUCT_ID = "0b0e5c6e-5b7a-4c2e-9a2f-1d3e4f5a6b7c"


def _outbox_insert(aggregate="product", aggregate_id=PRODUCT_ID, revision=1, event_type="updated"):
    async def work(conn):
        await conn.execute(text(
            "insert into outbox(aggregate, aggregate_id, revision, event_type) values (:a, :i, :r, :e)"),
            {"a": aggregate, "i": aggregate_id, "r": revision, "e": event_type})

    return work


def test_outbox_accepts_a_valid_row_with_defaults(pg_engine_factory):
    run(pg_engine_factory, _outbox_insert())

    async def read(conn):
        return tuple((await conn.execute(text("select attempts, processed_at, last_error from outbox"))).one())

    assert run(pg_engine_factory, read) == (0, None, None)


@pytest.mark.parametrize("kwargs", [
    {"aggregate": "order"},
    {"event_type": "deleted"},
    {"revision": -1},
])
def test_outbox_constraints_reject_bad_rows(pg_engine_factory, kwargs):
    with pytest.raises(IntegrityError):
        run(pg_engine_factory, _outbox_insert(**kwargs))


@pytest.mark.parametrize("aggregate_id", ["short", "64b7f0c2a1b2c3d4e5f60718", "not-a-uuid-at-all-not-a-uuid-at-all!"])
def test_outbox_aggregate_id_must_be_a_uuid(pg_engine_factory, aggregate_id):
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):          # the old 24-hex IDs and free text are no longer valid identifiers
        run(pg_engine_factory, _outbox_insert(aggregate_id=aggregate_id))


def test_outbox_is_idempotent_by_aggregate_revision_and_event(pg_engine_factory):
    run(pg_engine_factory, _outbox_insert())
    run(pg_engine_factory, _outbox_insert(revision=2))               # new revision is fine
    run(pg_engine_factory, _outbox_insert(event_type="archived"))    # new event type is fine
    with pytest.raises(IntegrityError):
        run(pg_engine_factory, _outbox_insert())                     # exact duplicate is not


def test_outbox_unprocessed_index_is_partial(pg_engine_factory):
    async def work(conn):
        return (await conn.execute(text(
            "select indexdef from pg_indexes where indexname = 'ix_outbox_unprocessed'"))).scalar()

    definition = run(pg_engine_factory, work)
    assert "WHERE (processed_at IS NULL)" in definition


def test_outbox_migration_upgrades_and_downgrades_one_step(pg_url, migrated_url):
    config = alembic_config(pg_url)

    async def tables(conn):
        return {r[0] for r in await conn.execute(text("select tablename from pg_tables where schemaname='public'"))}

    from database.pg import make_engine

    def present():
        async def go():
            engine = make_engine(pg_url)
            try:
                async with engine.begin() as conn:
                    return await tables(conn)
            finally:
                await engine.dispose()

        return asyncio.run(go())

    command.downgrade(config, "0001")
    assert "outbox" not in present() and "events" in present()   # only the outbox goes
    command.upgrade(config, "head")
    assert "outbox" in present()


def test_server_side_listing_event_and_cron_retention_job_on_real_postgres(pg_engine_factory, migrated_url, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from configuration.config import settings
    from database.pg import make_engine
    from events import recorder
    from workers.jobs import purge_events_job

    monkeypatch.setattr(settings, "session_signing_key", "integration-signing-key")

    async def scenario():
        engine = make_engine(migrated_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(recorder, "open_session", lambda: sessions())
        await recorder.record_server_event("impression", {"surface": "listing", "returned": 2}, None)
        async with engine.begin() as conn:
            await conn.execute(text("insert into events(session_id, type, created_at) values ('old', 'view', :t)"),
                               {"t": datetime.now(timezone.utc) - timedelta(days=30 * 19)})
        result = await purge_events_job({"pg_sessions": sessions})
        async with engine.begin() as conn:
            rows = (await conn.execute(text("select session_id, type from events"))).all()
        await engine.dispose()
        return result, [tuple(r) for r in rows]

    result, rows = asyncio.run(scenario())
    assert result == {"deleted": 1} and rows == [("unattributed", "impression")]


def test_database_spans_join_the_request_trace_and_hide_statements(pg_engine_factory, migrated_url, monkeypatch):
    from fastapi.testclient import TestClient
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from sqlalchemy.ext.asyncio import AsyncSession

    import main
    from configuration.config import settings
    from database.pg import get_pg_session, make_engine
    from observability import tracing

    exporter = InMemorySpanExporter()
    tracing.add_exporter(exporter)
    monkeypatch.setattr(settings, "session_signing_key", "integration-signing-key")
    monkeypatch.setattr(settings, "events_rate_limit_per_minute", 1000)
    app = main.create_app()

    async def real_session():
        engine = make_engine(migrated_url)
        try:
            async with AsyncSession(engine) as session:
                yield session
        finally:
            await engine.dispose()

    app.dependency_overrides[get_pg_session] = real_session
    parent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    secret = "private-search-text"
    response = TestClient(app).post(
        "/v1/events", json={"events": [{"type": "search", "payload": {"q": secret}}]}, headers={"traceparent": parent})
    assert response.status_code == 202

    finished = exporter.get_finished_spans()
    [request_span] = [s for s in finished if s.name == "http.request" and s.attributes.get("http.target") == "/v1/events"]
    queries = [s for s in finished if s.name == "db.query"]
    assert any(q.attributes["db.operation"] == "INSERT" for q in queries)
    for query in queries:
        assert format(query.context.trace_id, "032x") == "4bf92f3577b34da6a3ce929d0e0e4736"     # one trace
    assert any(q.parent.span_id == request_span.context.span_id for q in queries)                # child of the request
    assert secret not in str([dict(s.attributes) for s in finished])                              # no statements or params


def test_one_storefront_listing_is_one_connected_trace_from_request_to_database(pg_engine_factory, migrated_url, monkeypatch):
    """Browser traceparent -> API request span -> catalogue SELECT -> background impression INSERT: one trace."""
    from fastapi.testclient import TestClient
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import main
    from configuration.config import settings
    from database.pg import get_pg_session, make_engine
    from events import recorder
    from observability import tracing
    from repositories import products as catalogue
    from repositories.products import ProductInput, VariantInput

    exporter = InMemorySpanExporter()
    tracing.add_exporter(exporter)
    monkeypatch.setattr(settings, "session_signing_key", "integration-signing-key")
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1000)

    async def seed():
        engine = make_engine(migrated_url)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session, session.begin():
            await catalogue.create_product(session, ProductInput(
                slug="traced", name="Traced", cover_image_url="u", status="active",
                variants=[VariantInput(name="v", image_url="u", price=1, stock=1)]))
        await engine.dispose()

    import asyncio
    asyncio.run(seed())
    engine_holder = {}

    def open_session():
        engine = engine_holder.setdefault("engine", make_engine(migrated_url))
        return async_sessionmaker(engine, expire_on_commit=False)()

    async def request_session():
        engine = make_engine(migrated_url)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                yield session
        finally:
            await engine.dispose()

    monkeypatch.setattr(recorder, "open_session", open_session)
    app = main.create_app()
    app.dependency_overrides[get_pg_session] = request_session
    traceparent = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    response = TestClient(app).get("/products/", headers={"traceparent": traceparent})
    assert response.status_code == 200 and response.headers["x-trace-id"] == "0af7651916cd43dd8448eb211c80319c"
    assert [p["slug"] for p in response.json()["items"]] == ["traced"]

    finished = exporter.get_finished_spans()
    request_span = [s for s in finished if s.name == "http.request" and s.attributes.get("http.target") == "/products/"][-1]
    # (the seeding above also produced database spans, in their own traces; only this request's trace is examined)
    queries = [s for s in finished if s.name == "db.query"
               and format(s.context.trace_id, "032x") == "0af7651916cd43dd8448eb211c80319c"]
    operations = {q.attributes["db.operation"] for q in queries}
    assert {"SELECT", "INSERT"} <= operations, operations          # the catalogue read AND the event write are both spanned
    assert any(q.parent.span_id == request_span.context.span_id for q in queries)

    async def stored(conn):
        return tuple((await conn.execute(text("select type, payload->>'surface' from events"))).one())

    assert run(pg_engine_factory, stored) == ("impression", "listing")
