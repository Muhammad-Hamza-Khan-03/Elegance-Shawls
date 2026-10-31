"""M4 customer authentication on real PostgreSQL: exchange, server-side identity, hashed-only sessions, logout and revocation.

Offline: tokens are signed with a throwaway key and verified against an in-process JWKS; nothing leaves the machine.
"""
import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from database.pg import make_engine
from memory.principal import SESSION_HEADER, get_session_verifier
from routes.customer_auth_routes import router
from routes.memory_routes import router as memory_router
from security.customer_identity import ExternalIdentityVerifier, JwksCache
from security.customer_session import DbSessionVerifier, get_identity_verifier
from tests.customer_auth_support import AUDIENCE, ISSUER, claims, jwks, key, token
from tests.integration.api_support import ApiEnv

URL = "/v1/customer/auth"
MEMORY = "/v1/me/memory/consent"


class Keys:
    def __init__(self, doc):
        self.doc, self.fail = doc, False

    async def __call__(self):
        if self.fail:
            raise RuntimeError("jwks down")
        return self.doc


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    e = ApiEnv(migrated_url, monkeypatch)
    for k, v in {"customer_auth_enabled": True, "customer_auth_provider": "google", "customer_auth_issuer": ISSUER,
                 "customer_auth_audience": AUDIENCE, "customer_auth_jwks_url": "https://idp.test.invalid/jwks",
                 "customer_session_ttl_seconds": 3600, "customer_session_max_active": 5}.items():
        monkeypatch.setattr(settings, k, v)
    e.keys = Keys(jwks(key()))
    verifier = ExternalIdentityVerifier(issuer=ISSUER, audience=AUDIENCE, keys=JwksCache(e.keys))

    @asynccontextmanager
    async def sessions():                               # TestClient runs each request in its own loop: one engine per call
        engine = make_engine(migrated_url)
        try:
            async with AsyncSession(engine, expire_on_commit=False) as s:
                yield s
        finally:
            await engine.dispose()

    e.app.include_router(router)
    e.app.include_router(memory_router)
    e.app.dependency_overrides[get_identity_verifier] = lambda: verifier
    e.app.dependency_overrides[get_session_verifier] = lambda: DbSessionVerifier(sessions)
    return e


def exchange(env, sub="subject-123", **headers):
    return env.client.post(f"{URL}/exchange", json={"id_token": token(payload=claims(sub=sub))}, headers=headers)


def login(env, sub="subject-123") -> str:
    r = exchange(env, sub)
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def bearer(t) -> dict:
    return {SESSION_HEADER: t}


def count(env, table, where="true") -> int:
    return env.sql(f"select count(*) from {table} where {where}")[0][0]


# ---- exchange -----------------------------------------------------------------------------------
def test_exchange_provisions_a_registered_customer_and_a_working_session(env):
    r = exchange(env)
    body = r.json()
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert body["session_token"].startswith("cs1.") and set(body) == {"session_token", "expires_at"}
    assert env.sql("select c.status, i.provider, i.subject from customers c join customer_identities i on i.customer_id = c.id") \
        == [("registered", "google", "subject-123")]
    expires = datetime.fromisoformat(body["expires_at"])
    assert timedelta(minutes=59) < expires - datetime.now(timezone.utc) <= timedelta(hours=1)
    assert env.client.get(MEMORY, headers=bearer(body["session_token"])).status_code == 200


def test_only_the_token_hash_is_stored(env):
    t = login(env)
    assert env.sql("select token_hash from customer_sessions") == [(hashlib.sha256(t.encode()).hexdigest(),)]
    assert t not in repr(env.sql("select * from customer_sessions")) and t.split(".", 1)[1] not in repr(env.sql("select * from customer_sessions"))


def test_same_subject_gets_the_same_customer_and_a_different_subject_a_different_one(env):
    a1, a2, b = login(env), login(env), login(env, "subject-456")
    assert count(env, "customers") == 2 and count(env, "customer_identities") == 2 and count(env, "customer_sessions") == 3
    owners = env.sql("select customer_id, count(*) from customer_sessions group by customer_id order by 2")
    assert [n for _, n in owners] == [1, 2] and len({a1, a2, b}) == 3


def test_concurrent_first_logins_of_one_subject_make_one_customer(env):
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: exchange(env), range(4)))
    assert [r.status_code for r in results] == [200] * 4
    assert count(env, "customers") == 1 and count(env, "customer_identities") == 1 and count(env, "customer_sessions") == 4


def test_session_resolves_its_own_customer_not_a_client_supplied_one(env):
    victim = env.sql("insert into customers (status) values ('registered') returning id")[0][0]
    env.sql("insert into memory_consents (customer_id, granted, policy_version, changed_at) values (:c, true, 'v1', now())", c=victim)
    t = login(env)
    r = env.client.get(f"{MEMORY}?customer_id={victim}", headers={**bearer(t), "X-Customer-Id": str(victim), "X-Test-Customer": str(victim)})
    assert r.status_code == 200 and r.json()["granted"] is False                       # the victim's granted=true is not visible
    assert env.client.post(f"{URL}/exchange", json={"id_token": token(), "customer_id": str(victim)}).status_code == 422
    assert env.client.get(MEMORY, headers={"X-Customer-Id": str(victim)}).status_code == 401


@pytest.mark.parametrize("bad", [
    lambda: token(payload=claims(aud="someone-else")), lambda: token(payload=claims(iss="https://evil.invalid")),
    lambda: token(payload=claims(exp=1)), lambda: token(key(1), sign_with=key(2, "other")), lambda: "not-a-token",
])
def test_invalid_identity_tokens_are_401_and_create_nothing(env, bad):
    r = env.client.post(f"{URL}/exchange", json={"id_token": bad()})
    assert r.status_code == 401 and r.json() == {"detail": "Invalid identity token"}
    assert count(env, "customers") == 0 and count(env, "customer_identities") == 0 and count(env, "customer_sessions") == 0


def test_jwks_outage_is_503_and_creates_nothing(env):
    env.keys.fail = True
    r = exchange(env)
    assert r.status_code == 503 and count(env, "customers") == 0 and count(env, "customer_sessions") == 0


def test_session_cap_revokes_the_oldest_sessions(env, monkeypatch):
    monkeypatch.setattr(settings, "customer_session_max_active", 2)
    first, second, third = login(env), login(env), login(env)
    assert env.client.get(MEMORY, headers=bearer(first)).status_code == 401
    assert env.client.get(MEMORY, headers=bearer(second)).status_code == 200
    assert env.client.get(MEMORY, headers=bearer(third)).status_code == 200
    assert env.sql("select revoked_reason from customer_sessions where revoked_at is not null") == [("session_limit",)]


# ---- verifier: server-side checks ---------------------------------------------------------------
def test_unknown_expired_revoked_and_inactive_sessions_are_the_same_401(env):
    t = login(env)
    ok = env.client.get(MEMORY, headers=bearer(t))
    assert ok.status_code == 200
    responses = [env.client.get(MEMORY, headers=bearer("cs1." + "A" * 43)), env.client.get(MEMORY, headers=bearer(t[:-1])),
                 env.client.get(MEMORY)]
    env.sql("update customer_sessions set created_at = now() - interval '2 hours', expires_at = now() - interval '1 hour'")
    responses.append(env.client.get(MEMORY, headers=bearer(t)))
    assert {(r.status_code, r.text) for r in responses} == {(401, '{"detail":"Customer authentication is required"}')}


def test_session_of_a_non_registered_customer_is_refused(env):
    t = login(env)
    env.sql("update customers set status = 'anonymous'")
    assert env.client.get(MEMORY, headers=bearer(t)).status_code == 401


def test_deleting_a_customer_removes_its_sessions(env):
    login(env)
    env.sql("delete from customers")
    assert count(env, "customer_sessions") == 0


# ---- logout / revocation ------------------------------------------------------------------------
def test_logout_revokes_only_the_presented_session(env):
    keep, drop = login(env), login(env)
    r = env.client.post(f"{URL}/logout", headers=bearer(drop))
    assert r.status_code == 204
    assert env.client.get(MEMORY, headers=bearer(drop)).status_code == 401
    assert env.client.get(MEMORY, headers=bearer(keep)).status_code == 200
    assert env.sql("select revoked_reason from customer_sessions where revoked_at is not null") == [("logout",)]
    assert env.client.post(f"{URL}/logout", headers=bearer(drop)).status_code == 401           # already gone
    assert env.client.post(f"{URL}/logout").status_code == 401


def test_logout_all_revokes_every_session_of_that_customer_and_nobody_elses(env):
    a1, a2, b = login(env), login(env), login(env, "subject-456")
    r = env.client.post(f"{URL}/logout-all", headers=bearer(a1))
    assert r.status_code == 200 and r.json() == {"revoked": 2}
    assert env.client.get(MEMORY, headers=bearer(a1)).status_code == 401
    assert env.client.get(MEMORY, headers=bearer(a2)).status_code == 401
    assert env.client.get(MEMORY, headers=bearer(b)).status_code == 200
    assert env.sql("select distinct revoked_reason from customer_sessions where revoked_at is not null") == [("logout_all",)]


def test_a_revoked_session_cannot_be_revived_by_a_new_exchange_of_the_same_token(env):
    t = login(env)
    env.client.post(f"{URL}/logout", headers=bearer(t))
    assert exchange(env).json()["session_token"] != t
    assert env.client.get(MEMORY, headers=bearer(t)).status_code == 401


def test_admin_credentials_do_not_authenticate_customers(env):
    assert env.client.get(MEMORY, headers={"X-Admin-Key": "test-admin-key-that-is-long-enough", "X-Admin-Session": "es1.x"}).status_code == 401
    t = login(env)
    assert env.client.get("/v1/admin/accounts", headers=bearer(t)).status_code == 401


# ---- me ("is this session live?") -------------------------------------------------------------------
def test_me_reports_a_live_session_without_any_identity_data_and_dies_with_logout(env):
    t = login(env)
    r = env.client.get(f"{URL}/me", headers=bearer(t))
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert set(r.json()) == {"authenticated", "expires_at"} and r.json()["authenticated"] is True
    assert "subject-123" not in r.text
    assert env.client.post(f"{URL}/logout", headers=bearer(t)).status_code == 204
    assert env.client.get(f"{URL}/me", headers=bearer(t)).status_code == 401


def test_me_refuses_missing_and_unknown_sessions_alike(env):
    assert env.client.get(f"{URL}/me").status_code == 401
    assert env.client.get(f"{URL}/me", headers=bearer("cs1." + "x" * 43)).status_code == 401
