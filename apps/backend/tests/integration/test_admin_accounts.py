"""M1-S3: individual admin accounts on real PostgreSQL: sessions, roles, revocation, audit attribution, bootstrap."""
import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from configuration.config import settings
from repositories import Conflict
from repositories import admin as repo
from scripts.admin_accounts import CliError, bootstrap_owner, reset_password
from security.passwords import hash_password
from tests.integration.api_support import ADMIN_KEY, ApiEnv
from tests.integration.test_api_products import payload

PW = "correct horse battery"
PW_HASH = hash_password(PW)             # scrypt once; every seeded account shares it
SESSION = "X-Admin-Session"


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    env = ApiEnv(migrated_url, monkeypatch)
    monkeypatch.setattr(settings, "admin_api_key", "")
    monkeypatch.setattr(settings, "admin_legacy_key_expires_at", "")       # accounts only, unless a test reopens the window
    return env


def seed(env, email, role="editor", status="active") -> str:
    async def work(sessions):
        async with sessions() as session, session.begin():
            account = await repo.create_account(session, email=email, role=role, password_hash=PW_HASH)
            account.status = status
            return str(account.id)

    return env.run(work)


def login(env, email, password=PW):
    return env.client.post("/v1/admin/auth/login", json={"email": email, "password": password})


def sign_in(env, email) -> dict:
    response = login(env, email)
    assert response.status_code == 200, response.text
    return {SESSION: response.json()["token"]}


def audit(env, where="true"):
    return env.sql(f"select actor_type, actor_id, action, target, outcome, detail from audit_log where {where} order by created_at, id")


def count(env, table):
    return env.sql(f"select count(*) from {table}")[0][0]


# ---- login, session storage, uniform failures -------------------------------------------------
def test_login_issues_an_opaque_session_and_the_database_keeps_only_its_hash(env):
    seed(env, "owner@example.com", "owner")
    response = login(env, "Owner@Example.com ")               # email is case/space-insensitive
    assert response.status_code == 200
    token = response.json()["token"]
    assert token.startswith("es1.") and "password_hash" not in response.text
    stored = env.sql("select token_hash, expires_at - created_at from admin_sessions")
    assert stored[0][0] == hashlib.sha256(token.encode()).hexdigest() and token not in stored[0][0]
    assert abs(stored[0][1] - timedelta(seconds=settings.admin_session_ttl_seconds)) < timedelta(seconds=5)
    me = env.client.get("/v1/admin/auth/me", headers={SESSION: token}).json()
    assert me["role"] == "owner" and me["legacy"] is False and me["account"]["email"] == "owner@example.com"


def test_every_login_failure_is_the_same_401_and_is_audited_without_the_typed_email(env):
    seed(env, "active@example.com")
    seed(env, "off@example.com", status="disabled")
    attempts = [("ghost@example.com", PW), ("active@example.com", "wrong password!"), ("off@example.com", PW)]
    responses = [login(env, email, password) for email, password in attempts]
    assert {r.status_code for r in responses} == {401} and len({r.text for r in responses}) == 1
    assert [row[5]["reason"] for row in audit(env, "action = 'auth.login'")] == ["unknown_account", "bad_password", "account_disabled"]
    dump = str(env.sql("select * from audit_log"))
    assert "ghost@example.com" not in dump and "wrong password!" not in dump and PW not in dump
    assert count(env, "admin_sessions") == 0


def test_repeated_failures_lock_the_account_even_against_the_right_password_until_it_lapses(env, monkeypatch):
    monkeypatch.setattr(settings, "admin_login_max_failures", 3)
    seed(env, "victim@example.com")
    for _ in range(3):
        assert login(env, "victim@example.com", "wrong password!").status_code == 401
    assert login(env, "victim@example.com").status_code == 401                  # correct password, locked
    assert audit(env, "action = 'auth.login'")[-1][5]["reason"] == "account_locked"
    env.sql("update admin_accounts set locked_until = now() - interval '1 minute'")
    assert login(env, "victim@example.com").status_code == 200
    assert env.sql("select failed_login_count, locked_until from admin_accounts")[0] == (0, None)


# ---- logout, expiry, replay, isolation ---------------------------------------------------------
def test_logout_revokes_server_side_so_a_copied_token_cannot_be_replayed(env):
    seed(env, "editor@example.com")
    stolen = sign_in(env, "editor@example.com")
    assert env.client.get("/v1/admin/auth/me", headers=stolen).status_code == 200
    assert env.client.post("/v1/admin/auth/logout", headers=stolen).status_code == 200
    assert env.client.get("/v1/admin/auth/me", headers=stolen).status_code == 401
    assert env.client.post("/products/admin/", json=payload(), headers=stolen).status_code == 401
    assert env.client.get("/products/admin/", headers=stolen).status_code == 401
    assert env.sql("select revoked_reason from admin_sessions")[0][0] == "logout"
    assert count(env, "variants") == 0 and count(env, "products") == 0


def test_an_expired_session_is_rejected(env):
    seed(env, "editor@example.com")
    headers = sign_in(env, "editor@example.com")
    env.sql("update admin_sessions set created_at = now() - interval '2 hours', expires_at = now() - interval '1 hour'")
    assert env.client.get("/v1/admin/auth/me", headers=headers).status_code == 401
    assert env.client.get("/products/admin/", headers=headers).status_code == 401


def test_forged_and_malformed_session_tokens_are_rejected(env):
    seed(env, "editor@example.com")
    real = sign_in(env, "editor@example.com")[SESSION]
    for token in ("es1.forged", real + "x", real[:-1], "", " ", "Bearer " + real, "es1." + "A" * 43):
        assert env.client.get("/v1/admin/auth/me", headers={SESSION: token}).status_code == 401, token
    assert env.client.get("/v1/admin/auth/me", headers={SESSION: real}).status_code == 200


def test_sessions_are_isolated_per_account_and_per_login(env):
    seed(env, "a@example.com")
    seed(env, "b@example.com", "viewer")
    a1, a2, b = (sign_in(env, e) for e in ("a@example.com", "a@example.com", "b@example.com"))
    who = lambda h: env.client.get("/v1/admin/auth/me", headers=h).json()["account"]["email"]
    assert (who(a1), who(a2), who(b)) == ("a@example.com", "a@example.com", "b@example.com")
    assert env.client.post("/v1/admin/auth/logout", headers=a1).status_code == 200
    assert env.client.get("/v1/admin/auth/me", headers=a1).status_code == 401
    assert who(a2) == "a@example.com" and who(b) == "b@example.com"             # other sessions untouched
    assert env.client.post("/products/admin/", json=payload(), headers=b).status_code == 403   # B keeps B's role, not A's


# ---- revocation on privilege change ------------------------------------------------------------
def test_disabling_an_account_or_changing_its_role_kills_its_live_sessions(env):
    owner_id = seed(env, "owner@example.com", "owner")
    editor_id = seed(env, "editor@example.com")
    owner = sign_in(env, "owner@example.com")
    live = sign_in(env, "editor@example.com")
    patch = lambda body: env.client.patch(f"/v1/admin/accounts/{editor_id}", json=body, headers=owner)

    assert patch({"status": "disabled"}).status_code == 200
    assert env.client.get("/v1/admin/auth/me", headers=live).status_code == 401
    assert login(env, "editor@example.com").status_code == 401                   # disabled: cannot sign in either
    assert patch({"status": "active"}).status_code == 200
    assert env.client.get("/v1/admin/auth/me", headers=live).status_code == 401  # re-enabling does not resurrect it

    live = sign_in(env, "editor@example.com")
    assert patch({"role": "viewer"}).status_code == 200
    assert env.client.get("/v1/admin/auth/me", headers=live).status_code == 401  # no session outlives its old privileges
    assert env.client.get("/v1/admin/auth/me", headers=sign_in(env, "editor@example.com")).json()["role"] == "viewer"
    assert owner_id and env.client.get("/v1/admin/auth/me", headers=owner).status_code == 200


def test_password_change_and_owner_reset_revoke_every_session(env):
    seed(env, "owner@example.com", "owner")
    seed(env, "editor@example.com")
    owner = sign_in(env, "owner@example.com")
    first, second = sign_in(env, "editor@example.com"), sign_in(env, "editor@example.com")

    wrong = env.client.post("/v1/admin/auth/password", headers=first, json={"current_password": "not it at all!", "new_password": "a brand new passphrase"})
    assert wrong.status_code == 400 and env.client.get("/v1/admin/auth/me", headers=second).status_code == 200
    weak = env.client.post("/v1/admin/auth/password", headers=first, json={"current_password": PW, "new_password": "short"})
    assert weak.status_code == 422

    changed = env.client.post("/v1/admin/auth/password", headers=first, json={"current_password": PW, "new_password": "a brand new passphrase"})
    assert changed.status_code == 200
    rotated = {SESSION: changed.json()["token"]}
    assert rotated != first
    assert all(env.client.get("/v1/admin/auth/me", headers=h).status_code == 401 for h in (first, second))
    assert env.client.get("/v1/admin/auth/me", headers=rotated).status_code == 200
    assert login(env, "editor@example.com", PW).status_code == 401
    assert login(env, "editor@example.com", "a brand new passphrase").status_code == 200

    editor_id = env.sql("select id from admin_accounts where email = 'editor@example.com'")[0][0]
    reset = env.client.post(f"/v1/admin/accounts/{editor_id}/password", headers=owner, json={"new_password": "owner chosen passphrase"})
    assert reset.status_code == 200
    assert env.client.get("/v1/admin/auth/me", headers=rotated).status_code == 401
    assert login(env, "editor@example.com", "owner chosen passphrase").status_code == 200


# ---- roles -------------------------------------------------------------------------------------
def test_roles_are_enforced_by_the_server_and_denials_are_audited_against_the_account(env):
    viewer_id = seed(env, "viewer@example.com", "viewer")
    seed(env, "editor@example.com", "editor")
    seed(env, "owner@example.com", "owner")
    viewer, editor, owner = (sign_in(env, f"{r}@example.com") for r in ("viewer", "editor", "owner"))
    c, fake = env.client, uuid.uuid4()

    assert c.get("/products/admin/", headers=viewer).status_code == 200
    for method, path, body in (("post", "/products/admin/", payload()), ("patch", f"/products/admin/{fake}/status", {"status": "draft"}),
                               ("delete", f"/products/admin/{fake}", None), ("post", "/products/admin/ingestion/jobs", {})):
        assert c.request(method, path, json=body, headers=viewer).status_code == 403, path
    assert count(env, "products") == 0
    denied = audit(env, "outcome = 'denied'")
    assert len(denied) == 4 and {d[1] for d in denied} == {viewer_id}
    assert {d[5]["reason"] for d in denied} == {"insufficient_role"} and all(d[5]["status"] == 403 for d in denied)

    assert c.post("/products/admin/", json=payload(), headers=editor).status_code in (200, 201)
    for path in ("/v1/admin/accounts", "/v1/admin/audit", "/v1/admin/jobs/abc", "/v1/llm/models"):
        assert c.get(path, headers=editor).status_code == 403, path
    assert c.post("/v1/admin/accounts", headers=editor, json={"email": "x@example.com", "role": "owner", "password": PW}).status_code == 403
    assert count(env, "admin_accounts") == 3

    assert c.get("/v1/admin/accounts", headers=owner).status_code == 200
    assert c.get("/v1/admin/audit", headers=owner).status_code == 200
    anonymous = [c.get(p).status_code for p in ("/products/admin/", "/v1/admin/accounts", "/v1/admin/audit", "/v1/admin/auth/me")]
    assert anonymous == [401] * 4


def test_account_management_rules(env):
    seed(env, "owner@example.com", "owner")
    owner = sign_in(env, "owner@example.com")
    new = lambda **over: env.client.post("/v1/admin/accounts", headers=owner, json={"email": "new@example.com", "role": "editor", "password": PW, **over})

    created = new()
    assert created.status_code == 201 and "password_hash" not in created.text and PW not in created.text and created.json()["role"] == "editor"
    assert new(email="NEW@example.com").status_code == 409                              # duplicate, case-insensitive
    assert new(email="x@example.com", password="short").status_code == 422
    assert new(email="y@example.com", password="y@example.com").status_code == 422
    assert new(email="not-an-email").status_code == 422
    assert new(email="z@example.com", role="superuser").status_code == 422
    assert new(email="z@example.com", is_owner=True).status_code == 422                 # unknown fields are rejected
    assert login(env, "new@example.com").status_code == 200


def test_the_last_active_owner_can_never_be_removed_even_concurrently(env):
    first = seed(env, "one@example.com", "owner")
    owner = sign_in(env, "one@example.com")
    for body in ({"role": "editor"}, {"status": "disabled"}):
        response = env.client.patch(f"/v1/admin/accounts/{first}", json=body, headers=owner)
        assert response.status_code == 409 and "owner" in response.json()["detail"]
    second = seed(env, "two@example.com", "owner")

    async def race(sessions):
        async def demote(account_id):
            async with sessions() as session, session.begin():
                await repo.update_account(session, uuid.UUID(account_id), role="viewer")

        return await asyncio.gather(demote(first), demote(second), return_exceptions=True)

    results = env.run(race)
    assert sum(isinstance(r, Conflict) for r in results) == 1 and sum(r is None for r in results) == 1
    assert env.sql("select count(*) from admin_accounts where role = 'owner' and status = 'active'")[0][0] == 1


# ---- audit -------------------------------------------------------------------------------------
def test_every_mutation_is_attributed_finalised_and_reads_are_not_noise(env):
    editor_id = seed(env, "editor@example.com")
    editor = sign_in(env, "editor@example.com")
    c = env.client
    assert c.post("/products/admin/", json=payload("one"), headers=editor).status_code in (200, 201)
    assert c.post("/products/admin/", json=payload("one"), headers=editor).status_code == 409
    assert c.post("/products/admin/", json={"name": "bad"}, headers=editor).status_code == 422
    assert c.get("/products/admin/", headers=editor).status_code == 200

    rows = audit(env, "action like '% /products/admin/%'")
    assert [(r[1], r[2], r[4]) for r in rows] == [(editor_id, "POST /products/admin/", o) for o in ("success", "failure", "failure")]
    assert [r[5].get("status") for r in rows] == [None, 409, 422] and all(r[5]["role"] == "editor" for r in rows)
    assert not audit(env, "action like 'GET %'")
    env.client.patch(f"/products/admin/{uuid.uuid4()}/status", json={"status": "draft"}, headers=editor)
    assert audit(env, "action like 'PATCH %'")[0][2] == "PATCH /products/admin/{product_id}/status"
    assert not audit(env, "outcome = 'accepted'")                                  # nothing left half-recorded


def test_the_shared_key_is_attributed_to_itself_and_unauthenticated_writes_are_recorded(env, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", ADMIN_KEY)
    monkeypatch.setattr(settings, "admin_legacy_key_expires_at", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    assert env.client.post("/products/admin/", json=payload("legacy"), headers={"X-Admin-Key": ADMIN_KEY}).status_code in (200, 201)
    assert env.client.post("/products/admin/", json=payload("anon")).status_code == 401
    assert env.client.post("/products/admin/", json=payload("bad"), headers={"X-Admin-Key": "wrong"}).status_code == 401
    rows = audit(env, "action = 'POST /products/admin/'")
    assert [(r[1], r[4], (r[5] or {}).get("reason")) for r in rows] == [
        ("legacy-shared-key", "success", None), (None, "denied", "missing_credentials"), (None, "denied", "invalid_credentials")]
    assert ADMIN_KEY not in str(env.sql("select * from audit_log"))
    # and the window is closeable without a redeploy
    monkeypatch.setattr(settings, "admin_legacy_key_expires_at", (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
    assert env.client.get("/products/admin/", headers={"X-Admin-Key": ADMIN_KEY}).status_code == 401


def test_a_mutation_is_refused_when_its_audit_record_cannot_be_written(env, monkeypatch):
    seed(env, "editor@example.com")
    editor = sign_in(env, "editor@example.com")
    real = repo.add_audit

    async def broken(session, **kwargs):
        if kwargs["outcome"] == "accepted":
            raise RuntimeError("audit store down")
        return await real(session, **kwargs)

    monkeypatch.setattr(repo, "add_audit", broken)
    response = env.client.post("/products/admin/", json=payload("blocked"), headers=editor)
    assert response.status_code == 503 and "unavailable" in response.json()["detail"]
    assert count(env, "products") == 0
    assert env.client.get("/products/admin/", headers=editor).status_code == 200      # reads never needed the audit trail


def test_the_audit_log_is_append_only_apart_from_finalising_an_accepted_row(env):
    row = env.sql("insert into audit_log (actor_type, actor_id, action, outcome) values ('admin', 'x', 'POST /t', 'accepted') returning id")[0][0]
    env.sql("update audit_log set outcome = 'success', detail = cast(:d as jsonb) where id = :id", d='{"a": 1}', id=row)     # allowed once
    for statement in ("update audit_log set outcome = 'failure'", "update audit_log set action = 'other'",
                      "update audit_log set actor_id = 'someone-else'", "delete from audit_log"):
        with pytest.raises(Exception, match="append-only"):
            env.sql(statement)
    assert env.sql("select outcome, actor_id from audit_log")[0] == ("success", "x")


def test_audit_listing_is_newest_first_and_bounded(env):
    seed(env, "owner@example.com", "owner")
    owner = sign_in(env, "owner@example.com")
    for i in range(3):
        env.client.post("/v1/admin/accounts", headers=owner, json={"email": f"n{i}@example.com", "role": "viewer", "password": PW})
    items = env.client.get("/v1/admin/audit?limit=2", headers=owner).json()["items"]
    assert len(items) == 2 and items[0]["created_at"] >= items[1]["created_at"]
    assert env.client.get("/v1/admin/audit?limit=0", headers=owner).status_code == 422
    assert env.client.get("/v1/admin/audit?limit=201", headers=owner).status_code == 422


# ---- secret hygiene ----------------------------------------------------------------------------
def test_passwords_and_tokens_never_reach_responses_logs_or_the_audit_log(env, caplog):
    caplog.set_level(logging.DEBUG)
    seed(env, "owner@example.com", "owner")
    owner = sign_in(env, "owner@example.com")
    secret_pw = "Sup3r-secret-passphrase"
    outputs = [
        env.client.post("/v1/admin/accounts", headers=owner, json={"email": "e@example.com", "role": "editor", "password": secret_pw}).text,
        login(env, "e@example.com", secret_pw).text,
        login(env, "e@example.com", "wrong-secret-attempt").text,
        env.client.get("/v1/admin/accounts", headers=owner).text,
        env.client.get("/v1/admin/audit?limit=200", headers=owner).text,
        env.client.get("/v1/admin/auth/me", headers=owner).text,
    ]
    token = owner[SESSION]
    hidden = [secret_pw, "wrong-secret-attempt", PW, "scrypt$", "password_hash", "token_hash"]
    for text in outputs[:1] + outputs[2:]:
        assert not any(h in text for h in hidden + [token]), text[:200]
    assert not any(h in outputs[1] for h in ("scrypt$", "password_hash", "token_hash", secret_pw))
    database_dump = str(env.sql("select * from audit_log"))
    logs = caplog.text
    for forbidden in (secret_pw, "wrong-secret-attempt", PW, token, "scrypt$"):
        assert forbidden not in database_dump and forbidden not in logs


# ---- bootstrap CLI -----------------------------------------------------------------------------
def test_a_fresh_database_has_no_default_account_and_bootstrap_is_idempotent(env):
    assert count(env, "admin_accounts") == 0

    async def work(sessions):
        assert await bootstrap_owner(sessions, "First@Example.com", PW) == "created"
        assert await bootstrap_owner(sessions, "second@example.com", PW) == "exists"
        for weak in ("short", "third@example.com"):
            with pytest.raises(CliError):
                await bootstrap_owner(sessions, "third@example.com", weak)

    env.run(work)
    assert env.sql("select email, role, status from admin_accounts") == [("first@example.com", "owner", "active")]
    assert audit(env, "action = 'admin.bootstrap_owner'")[0][:2] == ("system", "cli")
    assert PW not in str(env.sql("select * from audit_log"))
    assert login(env, "first@example.com").status_code == 200


def test_concurrent_bootstraps_create_exactly_one_owner(env):
    async def work(sessions):
        return await asyncio.gather(*(bootstrap_owner(sessions, f"o{i}@example.com", PW) for i in range(5)))

    assert sorted(env.run(work)) == ["created"] + ["exists"] * 4
    assert count(env, "admin_accounts") == 1


def test_bootstrap_will_not_silently_promote_an_existing_non_owner_and_reset_revokes_sessions(env):
    seed(env, "editor@example.com")
    headers = sign_in(env, "editor@example.com")

    async def work(sessions):
        with pytest.raises(CliError, match="non-owner"):
            await bootstrap_owner(sessions, "editor@example.com", PW)
        with pytest.raises(CliError):
            await reset_password(sessions, "nobody@example.com", PW)
        await reset_password(sessions, "editor@example.com", "recovered passphrase")

    env.run(work)
    assert env.sql("select role from admin_accounts")[0][0] == "editor"
    assert env.client.get("/v1/admin/auth/me", headers=headers).status_code == 401
    assert login(env, "editor@example.com", "recovered passphrase").status_code == 200
    assert audit(env, "action = 'admin.reset_password'")[0][4] == "success"
