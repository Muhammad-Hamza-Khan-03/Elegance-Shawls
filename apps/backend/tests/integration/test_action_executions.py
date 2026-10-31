"""M3-S4: durable idempotency + audit for confirmed assistant actions on real PostgreSQL.

Each "worker" is its own engine/pool (as separate processes would be), so claims really race in the database. Disposable data; no
message is ever sent. The kernel/executor decisions themselves are covered by tests/test_action_executor.py.
"""
import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from actions import executor as x
from actions.store import LeaseLost, SqlExecutionStore
from database.pg import make_engine
from tests.integration.conftest import alembic_config
from tests.integration.repo_helpers import count, run_repo, tx
from tests.test_action_executor import _load, enquiry
from tests.test_action_kernel import KEY, catalogue

T0 = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
AUDIT_KEYS = {"version", "action_type", "outcome", "reason", "executed", "replayed", "fingerprint", "idempotency_key", "session_ref",
              "has_user", "product_ids", "variant_ids", "quantity_total", "enquiry_reference"}
INSERT_ENQUIRY = "insert into enquiries (reference, items, currency, total) values (:ref, '[{}]'::jsonb, 'PKR', 0)"


class Crash(BaseException):
    """A worker dying mid-request: not an Exception, so no handler in the executor may swallow it."""


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


def worker_store(factory, clock):
    """A fresh engine + session + store: one simulated worker process. Returns (store, session, engine)."""
    from sqlalchemy.ext.asyncio import AsyncSession

    engine = factory()
    session = AsyncSession(engine, expire_on_commit=False)
    return SqlExecutionStore(session, now=clock, lease_seconds=30), session, engine


async def close(*workers):
    for _, session, engine in workers:
        await session.close()
        await engine.dispose()


def writer(store, ref, delay=0.0, crash=False, fail=False):
    """A `perform` that creates an enquiry row through the store's own session, like the real adapter."""
    async def perform(action, params):
        await store.session.execute(text(INSERT_ENQUIRY), {"ref": ref})
        await asyncio.sleep(delay)
        if crash:
            raise Crash
        if fail:
            raise RuntimeError("password=hunter2")
        return {"reference": ref, "items": [], "total": 0, "currency": "PKR"}
    return perform


async def go(store, proposal, perform, audit=None):
    return await x.execute(proposal, confirmed=True, load_catalogue=_load(catalogue()), perform=perform, store=store,
                           audit=(audit or []).append if audit is not None else (lambda r: None))


async def rows(sessions):
    async with sessions() as s:
        return (await s.execute(text("select status, attempt, reason, replay_count, session_hash, audit, result "
                                     "from action_executions order by created_at"))).all()


def test_concurrent_workers_execute_one_enquiry_and_the_rest_replay_or_wait(pg_engine_factory):
    async def scenario(sessions):
        clock = Clock()
        workers = [worker_store(pg_engine_factory, clock) for _ in range(8)]
        try:
            outs = await asyncio.gather(*[go(w[0], enquiry(), writer(w[0], f"ES-W{n}AAAA", delay=0.2)) for n, w in enumerate(workers)])
            again = await go(workers[0][0], enquiry(), writer(workers[0][0], "ES-NEVERX"))
        finally:
            await close(*workers)
        return outs, again, await rows(sessions), await count(sessions, "enquiries")

    outs, again, table, enquiries = run_repo(pg_engine_factory, scenario)
    winners = [o for o in outs if o.outcome == "executed" and not o.replayed]
    assert len(winners) == 1 and enquiries == 1
    assert {o.reason for o in outs if o.outcome == "rejected"} <= {"execution_in_progress"}      # raced while pending: retryable, never a second execution
    assert all(o.result == winners[0].result for o in outs if o.outcome == "executed")
    assert again.replayed is True and again.result == winners[0].result                          # a later worker replays the durable result
    assert [(r.status, r.attempt) for r in table] == [("committed", 1)] and table[0].replay_count >= 1


def test_same_key_with_different_params_conflicts_across_workers(pg_engine_factory):
    async def scenario(sessions):
        clock = Clock()
        a, b = worker_store(pg_engine_factory, clock), worker_store(pg_engine_factory, clock)
        try:
            first = await go(a[0], enquiry(), writer(a[0], "ES-AAAAAA"))
            other = await go(b[0], enquiry(quantity=3), writer(b[0], "ES-BBBBBB"))
        finally:
            await close(a, b)
        return first, other, await count(sessions, "enquiries")

    first, other, enquiries = run_repo(pg_engine_factory, scenario)
    assert first.outcome == "executed" and (other.outcome, other.reason) == ("rejected", "idempotency_conflict") and enquiries == 1


def test_a_crash_after_claim_leaves_a_pending_row_and_no_enquiry_then_recovers_after_the_lease(pg_engine_factory):
    async def scenario(sessions):
        clock = Clock()
        dead, live = worker_store(pg_engine_factory, clock), worker_store(pg_engine_factory, clock)
        try:
            with pytest.raises(Crash):
                await go(dead[0], enquiry(), writer(dead[0], "ES-CRASHX", crash=True))
            await dead[1].close()                                                   # the process is gone; its transaction is gone with it
            mid = await rows(sessions), await count(sessions, "enquiries")
            early = await go(live[0], enquiry(), writer(live[0], "ES-EARLYX"))     # lease still live: must not double-run
            clock.now = T0 + timedelta(seconds=31)
            late = await go(live[0], enquiry(), writer(live[0], "ES-LATERX"))
        finally:
            await close(dead, live)
        return mid, early, late, await rows(sessions), await count(sessions, "enquiries")

    mid, early, late, table, enquiries = run_repo(pg_engine_factory, scenario)
    assert [(r.status, r.attempt) for r in mid[0]] == [("pending", 1)] and mid[1] == 0           # claim is durable, the half-done enquiry is not
    assert (early.outcome, early.reason) == ("rejected", "execution_in_progress")
    assert (late.outcome, late.result["reference"]) == ("executed", "ES-LATERX") and enquiries == 1
    assert [(r.status, r.attempt) for r in table] == [("committed", 2)]


def test_a_failed_attempt_is_durable_fixed_shape_and_retryable_with_the_same_key(pg_engine_factory):
    async def scenario(sessions):
        clock = Clock()
        w = worker_store(pg_engine_factory, clock)
        sink: list = []
        try:
            failed = await go(w[0], enquiry(), writer(w[0], "ES-FAILED", fail=True), sink)
            mid = await rows(sessions), await count(sessions, "enquiries")
            retry = await go(w[0], enquiry(), writer(w[0], "ES-RETRYX"))
        finally:
            await close(w)
        return failed, mid, retry, await rows(sessions), sink

    failed, mid, retry, table, sink = run_repo(pg_engine_factory, scenario)
    assert (failed.outcome, failed.reason) == ("rejected", "execution_failed")
    assert [(r.status, r.reason) for r in mid[0]] == [("failed", "execution_failed")] and mid[1] == 0   # enquiry insert rolled back with it
    assert "hunter2" not in json.dumps([sink, [dict(r._mapping) for r in mid[0]]], default=str)
    assert retry.outcome == "executed" and [(r.status, r.attempt, r.reason) for r in table] == [("committed", 2, None)]


def test_a_worker_that_lost_its_lease_cannot_commit_and_its_enquiry_is_rolled_back(pg_engine_factory):
    async def scenario(sessions):
        clock = Clock()
        slow, fast = worker_store(pg_engine_factory, clock), worker_store(pg_engine_factory, clock)
        try:
            kernel_claim = await slow[0].claim("sess-secret-123", KEY, "f" * 64, "start_whatsapp_enquiry", {"reason": "ok"}, create=True)
            clock.now = T0 + timedelta(seconds=31)                                   # slow stalls past its lease; fast takes over
            takeover = await fast[0].claim("sess-secret-123", KEY, "f" * 64, "start_whatsapp_enquiry", {"reason": "ok"}, create=True)
            with pytest.raises(LeaseLost):
                await slow[0].commit(kernel_claim, lambda: writer(slow[0], "ES-ZOMBIE")("x", {}))
            await fast[0].commit(takeover, lambda: writer(fast[0], "ES-WINNER")("x", {}))
        finally:
            await close(slow, fast)
        return kernel_claim, takeover, await rows(sessions), await count(sessions, "enquiries")

    first, takeover, table, enquiries = run_repo(pg_engine_factory, scenario)
    assert (first.state, takeover.state, takeover.attempt) == ("claimed", "claimed", 2)
    assert [(r.status, r.result["reference"]) for r in table] == [("committed", "ES-WINNER")] and enquiries == 1


def test_durable_audit_is_fixed_shape_and_holds_no_raw_session_params_or_prices(pg_engine_factory):
    async def scenario(sessions):
        w = worker_store(pg_engine_factory, Clock())
        try:
            await go(w[0], enquiry(), writer(w[0], "ES-AUDITX"))
        finally:
            await close(w)
        return await rows(sessions)

    (row,) = run_repo(pg_engine_factory, scenario)
    assert set(row.audit) == AUDIT_KEYS and row.audit["outcome"] == "executed" and row.audit["executed"] is True
    assert row.audit["enquiry_reference"] == "ES-AUDITX" and row.session_hash == hashlib.sha256(b"sess-secret-123").hexdigest()
    blob = json.dumps(row.audit)
    assert "sess-secret-123" not in blob and "user-pii-42" not in blob and "expected_unit_price" not in blob and "3500" not in blob


def test_stale_or_unconfirmed_requests_create_no_durable_row(pg_engine_factory):
    async def scenario(sessions):
        w = worker_store(pg_engine_factory, Clock())
        try:
            stale = await x.execute(enquiry(expected_unit_price=1), confirmed=True, load_catalogue=_load(catalogue()),
                                    perform=writer(w[0], "ES-STALEX"), store=w[0], audit=lambda r: None)
            unconfirmed = await x.execute(enquiry(), confirmed=False, load_catalogue=_load(catalogue()),
                                          perform=writer(w[0], "ES-UNCONF"), store=w[0], audit=lambda r: None)
        finally:
            await close(w)
        return stale, unconfirmed, await count(sessions, "action_executions"), await count(sessions, "enquiries")

    stale, unconfirmed, executions, enquiries = run_repo(pg_engine_factory, scenario)
    assert (stale.reason, unconfirmed.reason, executions, enquiries) == ("stale_price", "not_confirmed", 0, 0)


def test_table_constraints_refuse_impossible_states(pg_engine_factory):
    base = ("insert into action_executions (session_hash, idempotency_key, action_type, fingerprint, status, lease_expires_at, audit, result, reason) "
            "values (:h, :k, :a, :f, :s, now(), '{}'::jsonb, :res, :why)")
    ok = {"h": "a" * 64, "k": "idem_x", "a": "add_to_cart", "f": "b" * 64, "s": "pending", "res": None, "why": None}

    async def scenario(sessions):
        errors = []
        for n, over in enumerate([{"a": "place_order"}, {"s": "done"}, {"s": "committed"}, {"s": "failed"}, {"h": "short"}]):
            try:
                async with tx(sessions) as s:
                    await s.execute(text(base), {**ok, "k": f"idem_{n}", **over})
                errors.append(None)
            except IntegrityError as e:
                errors.append(type(e.orig).__name__)
        async with tx(sessions) as s:
            await s.execute(text(base), ok)
        try:
            async with tx(sessions) as s:
                await s.execute(text(base), ok)                                     # same (session, key)
        except IntegrityError as e:
            errors.append("unique" if "uq_action_executions" in str(e) else "other")
        return errors

    assert all(e for e in run_repo(pg_engine_factory, scenario))


def test_migration_0013_is_reversible_and_refuses_to_drop_records_silently(pg_url, migrated_url, monkeypatch):
    config = alembic_config(pg_url)

    def sql(statement):
        async def go_():
            engine = make_engine(pg_url)
            try:
                async with engine.begin() as conn:
                    r = await conn.execute(text(statement))
                    return r.all() if r.returns_rows else None
            finally:
                await engine.dispose()
        return asyncio.run(go_())

    sql("truncate action_executions")
    command.downgrade(config, "0012")
    assert sql("select to_regclass('action_executions')") == [(None,)]
    command.upgrade(config, "0013")
    sql("insert into action_executions (session_hash, idempotency_key, action_type, fingerprint, status, lease_expires_at, audit) "
        "values (repeat('a',64), 'idem_keep', 'add_to_cart', repeat('b',64), 'pending', now(), '{}')")
    monkeypatch.delenv("ALEMBIC_ALLOW_ACTION_EXECUTION_DATA_LOSS", raising=False)
    with pytest.raises(Exception, match="Refusing to downgrade 0013"):
        command.downgrade(config, "0012")
    assert sql("select count(*) from action_executions") == [(1,)]
    monkeypatch.setenv("ALEMBIC_ALLOW_ACTION_EXECUTION_DATA_LOSS", "1")
    command.downgrade(config, "0012")
    command.upgrade(config, "head")
