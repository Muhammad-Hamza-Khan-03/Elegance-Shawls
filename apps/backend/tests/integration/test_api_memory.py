"""M4-S1 explicit customer memory on real PostgreSQL: consent, isolation, idempotency, retention, audit-safe deletion, migration.

Disposable data only. Customer authentication does not exist yet, so the tests replace `memory_customer` with a header stand-in
(`X-Test-Customer`); the production default (always 401) is covered in tests/test_memory_policy.py.
"""
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from fastapi import Header, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from database.pg import make_engine
from memory import policy, service
from repositories import memory as repo
from routes.memory_routes import memory_customer, router
from schemas.memory_schema import MemoryCreate, MemoryUpdate
from tests.integration.api_support import ApiEnv
from tests.integration.conftest import alembic_config
from tests.integration.repo_helpers import count, run_repo, tx

URL = "/v1/me/memory"
T0 = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
SECRET = "zq-private-colour-xylophone"
SECRET_KEY, SECRET_REASON, SECRET_REF = "zqkeyxylophone", "zq-reason-xylophone", "ref:zq-xylophone"


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    e = ApiEnv(migrated_url, monkeypatch)

    async def who(x_test_customer: str | None = Header(default=None)) -> uuid.UUID:
        if not x_test_customer:
            raise HTTPException(401, "no customer")
        return uuid.UUID(x_test_customer)

    e.app.include_router(router)
    e.app.dependency_overrides[memory_customer] = who
    return e


def customer(env) -> dict:
    return {"X-Test-Customer": str(env.sql("insert into customers (status) values ('registered') returning id")[0][0])}


def idem() -> str:
    return "idem_" + uuid.uuid4().hex


def body(**over) -> dict:
    return {"idempotency_key": idem(), "category": "preference", "key": "style", "value": "plain designs", "source": "user_explicit", **over}


def opted_in(env) -> dict:
    h = customer(env)
    assert env.client.put(f"{URL}/consent", json={"granted": True}, headers=h).status_code == 200
    return h


def audit_actions(env) -> list[str]:
    return [r[0] for r in env.sql("select action from audit_log where action like 'memory.%' order by created_at, id")]


# ---- consent: off by default -------------------------------------------------------------------
def test_memory_is_off_by_default_and_nothing_works_without_opt_in(env):
    h = customer(env)
    assert env.client.get(f"{URL}/consent", headers=h).json()["granted"] is False
    assert env.client.get(URL, headers=h).status_code == 403
    r = env.client.post(URL, json=body(), headers=h)
    assert r.status_code == 403 and r.json()["detail"] == {"status": "rejected", "reason": "consent_required"}
    assert env.client.get(f"{URL}/{uuid.uuid4()}", headers=h).status_code == 403
    assert env.client.patch(f"{URL}/{uuid.uuid4()}", json={"value": "x"}, headers=h).status_code == 403
    assert count_items(env) == 0 and env.sql("select count(*) from memory_consents")[0][0] == 0


def test_requests_without_a_customer_are_401_and_change_nothing(env):
    assert env.client.post(URL, json=body()).status_code == 401
    assert env.client.put(f"{URL}/consent", json={"granted": True}).status_code == 401
    assert env.client.get(URL).status_code == 401 and audit_actions(env) == []


def test_consent_is_idempotent_audited_once_per_change_and_records_the_policy_version(env):
    h = customer(env)
    for _ in range(3):
        assert env.client.put(f"{URL}/consent", json={"granted": True}, headers=h).json()["policy_version"] == policy.MEMORY_POLICY_VERSION
    env.client.put(f"{URL}/consent", json={"granted": False}, headers=h)
    env.client.put(f"{URL}/consent", json={"granted": False}, headers=h)
    assert audit_actions(env) == ["memory.consent.grant", "memory.consent.revoke"]
    assert env.client.get(f"{URL}/consent", headers=h).json()["granted"] is False


def test_revoking_consent_hides_memories_and_regranting_shows_them_again(env):
    h = opted_in(env)
    created = env.client.post(URL, json=body(), headers=h).json()
    env.client.put(f"{URL}/consent", json={"granted": False}, headers=h)
    assert env.client.get(URL, headers=h).status_code == 403 and env.client.get(f"{URL}/{created['id']}", headers=h).status_code == 403
    assert env.client.post(URL, json=body(key="other"), headers=h).status_code == 403
    env.client.put(f"{URL}/consent", json={"granted": True}, headers=h)
    assert [i["id"] for i in env.client.get(URL, headers=h).json()["items"]] == [created["id"]]


def test_a_customer_can_erase_everything_without_consent(env):
    h = opted_in(env)
    env.client.post(URL, json=body(key="a"), headers=h)
    env.client.post(URL, json=body(key="b"), headers=h)
    env.client.put(f"{URL}/consent", json={"granted": False}, headers=h)
    r = env.client.delete(URL, headers=h)
    assert r.status_code == 200 and r.json() == {"deleted": 2}
    assert env.client.delete(URL, headers=h).json() == {"deleted": 0}
    assert env.sql("select count(*) from memory_items where status = 'active'")[0][0] == 0


# ---- create / list / view / correct / delete ---------------------------------------------------
def test_full_lifecycle_with_provenance_reason_and_no_internal_fields(env):
    h = opted_in(env)
    r = env.client.post(URL, json=body(source="memory_page", source_ref="msg:abc123", reason="said so on the memory page", retention_days=30), headers=h)
    assert r.status_code == 201
    item = r.json()
    assert set(item) == {"id", "category", "key", "value", "source", "source_ref", "reason", "version", "retention_days", "expires_at",
                         "created_at", "updated_at"}
    assert (item["source"], item["source_ref"], item["reason"], item["version"], item["retention_days"]) == ("memory_page", "msg:abc123", "said so on the memory page", 1, 30)
    assert env.client.get(f"{URL}/{item['id']}", headers=h).json() == item
    listed = env.client.get(URL, headers=h).json()
    assert listed == {"items": [item], "next_cursor": None}

    fixed = env.client.patch(f"{URL}/{item['id']}", json={"value": "plain, light designs"}, headers=h)
    assert fixed.status_code == 200 and fixed.json()["value"] == "plain, light designs" and fixed.json()["version"] == 2
    assert (fixed.json()["key"], fixed.json()["source"], fixed.json()["reason"]) == ("style", "memory_page", "said so on the memory page")

    assert env.client.delete(f"{URL}/{item['id']}", headers=h).status_code == 204
    assert env.client.get(f"{URL}/{item['id']}", headers=h).status_code == 404
    assert env.client.get(URL, headers=h).json()["items"] == []
    assert audit_actions(env) == ["memory.consent.grant", "memory.create", "memory.update", "memory.delete"]


def test_create_replay_returns_the_same_item_without_a_second_row_or_audit(env):
    h = opted_in(env)
    req = body()
    first = env.client.post(URL, json=req, headers=h)
    again = env.client.post(URL, json=req, headers=h)
    assert (first.status_code, again.status_code) == (201, 200) and first.json() == again.json()
    assert count_items(env) == 1 and audit_actions(env).count("memory.create") == 1


def test_same_idempotency_key_with_different_content_is_a_conflict(env):
    h = opted_in(env)
    req = body()
    env.client.post(URL, json=req, headers=h)
    r = env.client.post(URL, json={**req, "value": "something else"}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "idempotency_conflict"
    assert env.client.get(URL, headers=h).json()["items"][0]["value"] == "plain designs"


def test_a_second_live_memory_with_the_same_key_is_refused_until_the_first_is_deleted(env):
    h = opted_in(env)
    first = env.client.post(URL, json=body(), headers=h).json()
    assert env.client.post(URL, json=body(value="other"), headers=h).json()["detail"]["reason"] == "duplicate_key"
    env.client.delete(f"{URL}/{first['id']}", headers=h)
    assert env.client.post(URL, json=body(value="other"), headers=h).status_code == 201


def test_update_is_idempotent_and_only_a_real_change_bumps_version_and_audits(env):
    h = opted_in(env)
    item = env.client.post(URL, json=body(), headers=h).json()
    for _ in range(3):
        r = env.client.patch(f"{URL}/{item['id']}", json={"value": "new value"}, headers=h)
    assert r.json()["version"] == 2
    noop = env.client.patch(f"{URL}/{item['id']}", json={"value": "new value", "reason": None}, headers=h)
    assert noop.json() == r.json() and audit_actions(env).count("memory.update") == 1


def test_delete_is_idempotent_and_a_replayed_create_cannot_resurrect_it(env):
    h = opted_in(env)
    req = body()
    item = env.client.post(URL, json=req, headers=h).json()
    assert [env.client.delete(f"{URL}/{item['id']}", headers=h).status_code for _ in range(3)] == [204, 204, 204]
    assert audit_actions(env).count("memory.delete") == 1
    r = env.client.post(URL, json=req, headers=h)
    assert r.status_code == 410 and r.json()["detail"]["reason"] == "gone" and env.client.get(URL, headers=h).json()["items"] == []


def test_the_per_customer_cap_is_enforced(env, monkeypatch):
    monkeypatch.setattr(policy, "MAX_ACTIVE_ITEMS", 3)
    h = opted_in(env)
    codes = [env.client.post(URL, json=body(key=f"k{i}"), headers=h).status_code for i in range(4)]
    assert codes == [201, 201, 201, 409]
    env.client.delete(URL, headers=h)
    assert env.client.post(URL, json=body(key="k9"), headers=h).status_code == 201


@pytest.mark.parametrize("over", [
    {"value": "reach me at a@b.co"}, {"value": "0300 1234567"}, {"value": ""}, {"value": "x" * 201}, {"value": "tab\there"},
    {"category": "weak_signal"}, {"source": "model_inferred"}, {"key": "Bad Key"}, {"retention_days": 9999}, {"retention_days": "10"},
    {"idempotency_key": "bad"}, {"customer_id": str(uuid.uuid4())}, {"id": str(uuid.uuid4())}, {"expires_at": "2099-01-01T00:00:00Z"},
])
def test_malformed_create_is_422_and_stores_nothing(env, over):
    h = opted_in(env)
    assert env.client.post(URL, json=body(**over), headers=h).status_code == 422
    assert count_items(env) == 0


def test_malformed_requests_of_other_kinds_are_422(env):
    h = opted_in(env)
    item = env.client.post(URL, json=body(), headers=h).json()
    for payload in ({}, {"key": "renamed"}, {"value": "a@b.co"}, {"value": None}):
        assert env.client.patch(f"{URL}/{item['id']}", json=payload, headers=h).status_code == 422
    assert env.client.get(f"{URL}/not-a-uuid", headers=h).status_code == 422
    assert env.client.delete(f"{URL}/not-a-uuid", headers=h).status_code == 422
    assert env.client.put(f"{URL}/consent", json={"granted": "true"}, headers=h).status_code == 422
    assert env.client.post(URL, content="[1]", headers={**h, "content-type": "application/json"}).status_code == 422
    assert env.client.get(f"{URL}/{item['id']}", headers=h).json()["value"] == "plain designs"


# ---- isolation -----------------------------------------------------------------------------------
def test_customers_cannot_see_change_or_delete_each_others_memory(env):
    a, b = opted_in(env), opted_in(env)
    mine = env.client.post(URL, json=body(value=SECRET), headers=a).json()

    assert env.client.get(URL, headers=b).json()["items"] == []
    assert env.client.get(f"{URL}/{mine['id']}", headers=b).status_code == 404
    assert env.client.get(f"{URL}/{uuid.uuid4()}", headers=b).status_code == 404            # same answer as for a real foreign id
    assert env.client.patch(f"{URL}/{mine['id']}", json={"value": "hijacked"}, headers=b).status_code == 404
    assert env.client.delete(f"{URL}/{mine['id']}", headers=b).status_code == 204           # indistinguishable no-op
    assert env.client.delete(URL, headers=b).json() == {"deleted": 0}

    assert env.client.get(f"{URL}/{mine['id']}", headers=a).json()["value"] == SECRET
    assert audit_actions(env).count("memory.delete") == 0


def test_the_same_idempotency_key_and_key_name_in_two_accounts_never_collide_or_leak(env):
    a, b = opted_in(env), opted_in(env)
    req = body(value="a's value")
    ra = env.client.post(URL, json=req, headers=a).json()
    rb = env.client.post(URL, json={**req, "value": "b's value"}, headers=b)                # same idem key, different customer
    assert rb.status_code == 201 and rb.json()["id"] != ra["id"] and rb.json()["value"] == "b's value"
    assert env.client.get(URL, headers=a).json()["items"][0]["value"] == "a's value"


def test_consent_is_per_customer(env):
    a, b = opted_in(env), customer(env)
    assert env.client.post(URL, json=body(), headers=a).status_code == 201
    assert env.client.post(URL, json=body(), headers=b).status_code == 403


def test_a_customer_that_does_not_exist_cannot_gain_consent_or_memory(pg_engine_factory):
    ghost = uuid.uuid4()

    async def scenario(sessions):
        with pytest.raises(IntegrityError):
            async with tx(sessions) as s:
                await repo.set_consent(s, ghost, True, policy.MEMORY_POLICY_VERSION, T0)
        return await count(sessions, "memory_consents")

    assert run_repo(pg_engine_factory, scenario) == 0


# ---- audit safety --------------------------------------------------------------------------------
def test_no_audit_row_or_deleted_row_ever_contains_memory_content(env):
    h = opted_in(env)
    item = env.client.post(URL, json=body(key=SECRET_KEY, value=SECRET, reason=SECRET_REASON, source_ref=SECRET_REF), headers=h).json()
    env.client.patch(f"{URL}/{item['id']}", json={"value": SECRET + "-v2", "reason": SECRET_REASON + "2"}, headers=h)
    assert "xylophone" in env.sql("select memory_items::text from memory_items")[0][0]       # the live row really holds it
    env.client.delete(f"{URL}/{item['id']}", headers=h)

    assert audit_actions(env) == ["memory.consent.grant", "memory.create", "memory.update", "memory.delete"]
    assert env.sql("select count(*) from audit_log where audit_log::text ilike '%xylophone%'")[0][0] == 0
    assert env.sql("select count(*) from memory_items where memory_items::text ilike '%xylophone%'")[0][0] == 0
    tomb = env.sql("select status, key, value, reason, source_ref, fingerprint, deleted_at is not null, category from memory_items")[0]
    assert tomb == ("deleted", None, None, None, None, None, True, "preference")
    detail = env.sql("select detail from audit_log where action = 'memory.update'")[0][0]
    assert detail == {"policy_version": policy.MEMORY_POLICY_VERSION, "category": "preference", "fields": ["reason", "value"]}


def test_if_the_audit_write_fails_the_change_is_rolled_back(env):
    h = opted_in(env)
    env.sql("alter table audit_log add constraint no_memory_audit check (action not like 'memory.create%') not valid")
    try:
        with pytest.raises(Exception):
            env.client.post(URL, json=body(), headers=h)
    finally:
        env.sql("alter table audit_log drop constraint no_memory_audit")
    assert count_items(env) == 0


# ---- retention -----------------------------------------------------------------------------------
def test_expired_memory_is_hidden_unrecoverable_and_purged(pg_engine_factory):
    cid = uuid.uuid4()

    async def scenario(sessions):
        async with tx(sessions) as s:
            await s.execute(text("insert into customers (id, status) values (:id, 'registered')"), {"id": cid})
            await service.set_consent(s, cid, True, T0)
            first, _ = await service.create(s, cid, MemoryCreate(**body(key="short", retention_days=1)), T0)
            second, _ = await service.create(s, cid, MemoryCreate(**body(key="long", retention_days=100)), T0)
        later = T0 + timedelta(days=2)
        async with tx(sessions) as s:
            assert [i.key for i in await service.list_items(s, cid, later)] == ["long"]
            with pytest.raises(service.MemoryRejected) as gone:
                await service.get_item(s, cid, first.id, later)
            assert gone.value.reason == "not_found"
        async with tx(sessions) as s:
            assert await service.purge_expired(s, later) == (1, 0)
            assert await service.purge_expired(s, later) == (0, 0)
        async with tx(sessions) as s:
            row = (await s.execute(text("select status, key, value from memory_items where id = :i"), {"i": first.id})).one()
            assert row == ("deleted", None, None)
            with pytest.raises(service.MemoryRejected) as replay:
                await service.create(s, cid, MemoryCreate(**{**body(key="short", retention_days=1), "idempotency_key": first.idempotency_key}), later)
            assert replay.value.reason == "gone"
        async with tx(sessions) as s:                                                      # the key name is reusable once expired
            assert (await service.create(s, cid, MemoryCreate(**body(key="short")), later))[0].key == "short"
        async with tx(sessions) as s:
            assert await service.purge_expired(s, later + timedelta(days=policy.TOMBSTONE_DAYS + 1)) == (0, 1)
        return await count(sessions, "memory_items")

    assert run_repo(pg_engine_factory, scenario) == 2


def test_a_real_correction_restarts_the_retention_window_but_a_repeat_does_not(pg_engine_factory):
    cid = uuid.uuid4()

    async def scenario(sessions):
        async with tx(sessions) as s:
            await s.execute(text("insert into customers (id, status) values (:id, 'registered')"), {"id": cid})
            await service.set_consent(s, cid, True, T0)
            item, _ = await service.create(s, cid, MemoryCreate(**body(retention_days=10)), T0)
        t1 = T0 + timedelta(days=6)
        async with tx(sessions) as s:
            changed = await service.update(s, cid, item.id, MemoryUpdate(value="fresh"), t1)
        async with tx(sessions) as s:
            repeat = await service.update(s, cid, item.id, MemoryUpdate(value="fresh"), t1 + timedelta(days=2))
        return changed.expires_at, repeat.expires_at, repeat.version

    changed, repeat, version = run_repo(pg_engine_factory, scenario)
    assert changed == T0 + timedelta(days=16) and repeat == changed and version == 2


# ---- concurrency ---------------------------------------------------------------------------------
def test_simultaneous_identical_creates_make_one_memory(env):
    h = opted_in(env)
    req = body()
    with ThreadPoolExecutor(8) as pool:
        replies = list(pool.map(lambda _: env.client.post(URL, json=req, headers=h), range(8)))
    assert sorted({r.status_code for r in replies}) == [200, 201] and sum(r.status_code == 201 for r in replies) == 1
    assert count_items(env) == 1 and audit_actions(env).count("memory.create") == 1


def test_simultaneous_different_keys_for_one_name_make_one_memory(env):
    h = opted_in(env)
    with ThreadPoolExecutor(8) as pool:
        replies = list(pool.map(lambda _: env.client.post(URL, json=body(), headers=h), range(8)))
    assert sum(r.status_code == 201 for r in replies) == 1 and all(r.status_code in (201, 409) for r in replies) and count_items(env) == 1


# ---- database guarantees -------------------------------------------------------------------------
def test_the_database_itself_refuses_inferred_categories_unscrubbed_tombstones_and_overlong_content(env):
    h = opted_in(env)
    cid = h["X-Test-Customer"]
    ok = ("insert into memory_items (customer_id, idempotency_key, category, key, value, source, fingerprint, retention_days, expires_at) "
          "values (:c, :i, :cat, 'k', :v, :src, repeat('a', 64), 10, now() + interval '1 day')")
    base = {"c": cid, "i": "idem_" + "x" * 20, "cat": "preference", "v": "v", "src": "user_explicit"}
    for bad in ({"cat": "weak_signal"}, {"src": "model_inferred"}, {"v": "x" * 201}, {"i": "nope"}):
        with pytest.raises(Exception):
            env.sql(ok, **{**base, **bad})
    with pytest.raises(Exception):                      # a tombstone that kept content
        env.sql("insert into memory_items (customer_id, idempotency_key, category, key, status, source, retention_days, expires_at, deleted_at) "
                "values (:c, :i, 'preference', 'k', 'deleted', 'user_explicit', 10, now() + interval '1 day', now())", c=cid, i=base["i"])
    assert count_items(env) == 0


def test_deleting_a_customer_removes_their_consent_and_memories(env):
    h = opted_in(env)
    env.client.post(URL, json=body(), headers=h)
    env.sql("delete from customers where id = :c", c=h["X-Test-Customer"])
    assert count_items(env) == 0 and env.sql("select count(*) from memory_consents")[0][0] == 0


def count_items(env) -> int:
    return env.sql("select count(*) from memory_items")[0][0]


def test_migration_0014_is_reversible_and_refuses_to_drop_memory_silently(pg_url, migrated_url, monkeypatch):
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

    sql("truncate memory_items, memory_consents, customers cascade")
    command.downgrade(config, "0013")
    assert sql("select to_regclass('memory_items'), to_regclass('memory_consents')") == [(None, None)]
    command.upgrade(config, "0014")
    sql("insert into customers (id, status) values ('00000000-0000-0000-0000-000000000001', 'registered')")
    sql("insert into memory_consents (customer_id, granted, policy_version, changed_at) values ('00000000-0000-0000-0000-000000000001', true, 'v', now())")
    monkeypatch.delenv("ALEMBIC_ALLOW_MEMORY_DATA_LOSS", raising=False)
    with pytest.raises(Exception, match="Refusing to downgrade 0014"):
        command.downgrade(config, "0013")
    assert sql("select count(*) from memory_consents") == [(1,)]
    monkeypatch.setenv("ALEMBIC_ALLOW_MEMORY_DATA_LOSS", "1")
    command.downgrade(config, "0013")
    assert sql("select to_regclass('memory_items')") == [(None,)]
    command.upgrade(config, "head")
    sql("truncate customers cascade")


# ---- M4-S2: real principal seam (no memory_customer override) --------------------------------------
def test_session_principals_isolate_customers_end_to_end(env):
    import hashlib

    from memory.principal import SESSION_HEADER, CustomerPrincipal, get_session_verifier

    ids = {t: env.sql("insert into customers (status) values ('registered') returning id")[0][0] for t in ("cs1.a", "cs1.b")}

    class Store:
        async def verify(self, token, now):
            cid = ids.get(token)
            return cid and CustomerPrincipal(cid, "s-" + token, hashlib.sha256(token.encode()).hexdigest(), now + timedelta(hours=1))

    del env.app.dependency_overrides[memory_customer]
    env.app.dependency_overrides[get_session_verifier] = lambda: Store()
    a, b = {SESSION_HEADER: "cs1.a"}, {SESSION_HEADER: "cs1.b"}
    assert env.client.put(f"{URL}/consent", json={"granted": True}, headers=a).status_code == 200
    item = env.client.post(URL, json=body(), headers=a).json()
    assert env.client.get(f"{URL}/{item['id']}", headers=a).status_code == 200
    # b's own session can neither see nor change a's item, and a client-supplied customer id changes nothing
    spoof = {**b, "X-Test-Customer": str(ids["cs1.a"]), "X-Customer-Id": str(ids["cs1.a"])}
    assert env.client.get(f"{URL}/{item['id']}", headers=spoof).status_code == 403  # b has no consent
    assert env.client.put(f"{URL}/consent", json={"granted": True}, headers=b).status_code == 200
    assert env.client.get(f"{URL}/{item['id']}", headers=spoof).status_code == 404
    assert env.client.delete(f"{URL}/{item['id']}", headers=spoof).status_code == 204  # idempotent, deletes nothing of a's
    assert env.client.get(URL, headers={SESSION_HEADER: "cs1.unknown"}).status_code == 401
    assert env.client.get(f"{URL}/{item['id']}", headers=a).status_code == 200
