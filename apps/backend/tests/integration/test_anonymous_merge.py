"""Synthetic login and anonymous event merge on disposable PostgreSQL only."""
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from configuration.config import settings
from events.session import mint_session_token, verify_session_token
from tests.integration.test_api_customer_auth import URL, bearer, count, env, login
from tests.customer_auth_support import token
from tests.customer_auth_synthetic import SyntheticPhoneOtpProvider

MERGE = f"{URL}/merge-anonymous"


def enable_merge(monkeypatch):
    monkeypatch.setattr(settings, "environment", "staging")
    monkeypatch.setattr(settings, "customer_anonymous_merge_enabled", True)
    monkeypatch.setattr(settings, "session_signing_key", "synthetic-merge-key")


def source(e, *, age=0, owner=None):
    token = mint_session_token()
    sid = verify_session_token(token)
    e.sql("insert into events (session_id, type, customer_id, created_at) values (:s, 'view', :c, :t)",
          s=sid, c=owner, t=datetime.now(timezone.utc) - timedelta(seconds=age))
    return token, sid


def merge(e, session, anon, consent=True, **extra):
    return e.client.post(MERGE, json={"consent": consent, **extra},
                         headers={**bearer(session), "X-Anonymous-Session": anon})


def test_merge_is_one_way_audited_and_idempotent(env, monkeypatch):
    enable_merge(monkeypatch)
    customer_session = login(env)
    anon, sid = source(env)
    first = merge(env, customer_session, anon)
    assert first.status_code == 200 and first.json() == {"merged": 1, "replayed": False}
    assert merge(env, customer_session, anon).json() == {"merged": 1, "replayed": True}
    owner = env.sql("select customer_id from customer_sessions")[0][0]
    assert env.sql("select customer_id from events where session_id = :s", s=sid) == [(owner,)]
    assert count(env, "anonymous_merges") == 1
    assert count(env, "audit_log", "action = 'customer.merge_anonymous'") == 1
    assert count(env, "memory_items") == 0


def test_merge_refuses_other_customer_and_conflicting_event_owner(env, monkeypatch):
    enable_merge(monkeypatch)
    a, b = login(env), login(env, "other-subject")
    anon, sid = source(env)
    assert merge(env, a, anon).status_code == 200
    assert merge(env, b, anon).status_code == 409
    second, second_id = source(env, owner=env.sql("select customer_id from customer_sessions where token_hash = :h",
                          h=hashlib.sha256(a.encode()).hexdigest())[0][0])
    assert merge(env, b, second).status_code == 409
    assert count(env, "anonymous_merges") == 1
    assert env.sql("select customer_id from events where session_id = :s", s=second_id)[0][0] != env.sql(
        "select customer_id from customer_sessions where token_hash = :h", h=hashlib.sha256(b.encode()).hexdigest())[0][0]


def test_merge_fails_closed_on_consent_freshness_and_bad_ownership_proof(env, monkeypatch):
    enable_merge(monkeypatch)
    session = login(env)
    anon, sid = source(env, age=2 * 86400)
    assert merge(env, session, anon).status_code == 409
    assert merge(env, session, anon, False).status_code == 403
    assert merge(env, session, anon + "x").status_code == 403
    assert merge(env, session, anon, True, customer_id="any").status_code == 422
    assert env.client.post(MERGE, json={"consent": True}, headers={"X-Anonymous-Session": anon}).status_code == 401
    assert count(env, "anonymous_merges") == 0 and count(env, "audit_log", "action = 'customer.merge_anonymous'") == 0
    assert env.sql("select customer_id from events where session_id = :s", s=sid) == [(None,)]


def test_merge_is_unavailable_without_staging_flag_and_refuses_tracking_opt_out(env, monkeypatch):
    monkeypatch.setattr(settings, "session_signing_key", "synthetic-merge-key")
    session = login(env)
    anon, sid = source(env)
    assert merge(env, session, anon).status_code == 404
    enable_merge(monkeypatch)
    assert env.client.post(MERGE, json={"consent": True}, headers={**bearer(session), "X-Anonymous-Session": anon,
                                                             "Sec-GPC": "1"}).status_code == 403
    assert env.sql("select customer_id from events where session_id = :s", s=sid) == [(None,)]


def test_new_anonymous_events_after_merge_are_not_silently_attributed(env, monkeypatch):
    enable_merge(monkeypatch)
    session = login(env)
    anon, sid = source(env)
    assert merge(env, session, anon).status_code == 200
    env.sql("insert into events (session_id, type) values (:s, 'click')", s=sid)
    response = merge(env, session, anon)
    assert response.status_code == 409 and response.json()["detail"]["reason"] == "source_changed"
    assert count(env, "anonymous_merges") == 1
    assert count(env, "audit_log", "action = 'customer.merge_anonymous'") == 1
    assert count(env, "events", "customer_id is null") == 1


def test_merge_never_changes_explicit_authenticated_memory(env, monkeypatch):
    enable_merge(monkeypatch)
    customer_session = login(env)
    headers = bearer(customer_session)
    assert env.client.put("/v1/me/memory/consent", json={"granted": True}, headers=headers).status_code == 200
    explicit = {"idempotency_key": "idem_explicitmemory01", "category": "preference", "key": "colour",
                "value": "blue", "source": "user_explicit"}
    assert env.client.post("/v1/me/memory", json=explicit, headers=headers).status_code == 201
    anon, _ = source(env)
    assert merge(env, customer_session, anon).status_code == 200
    assert env.sql("select key, value, source from memory_items where status = 'active'") == [("colour", "blue", "user_explicit")]
    assert count(env, "memory_items") == 1


def test_audit_failure_rolls_back_event_attribution_and_ledger(env, monkeypatch):
    enable_merge(monkeypatch)
    customer_session = login(env)
    anon, sid = source(env)

    async def failed_audit(*args, **kwargs):
        raise RuntimeError("synthetic audit outage")

    monkeypatch.setattr("identity.merge.audit.add_audit", failed_audit)
    response = TestClient(env.app, raise_server_exceptions=False).post(
        MERGE, json={"consent": True}, headers={**bearer(customer_session), "X-Anonymous-Session": anon})
    assert response.status_code == 503
    assert env.sql("select customer_id from events where session_id = :s", s=sid) == [(None,)]
    assert count(env, "anonymous_merges") == 0


def test_verified_issuer_is_part_of_customer_identity_key(env):
    from security.customer_identity import ExternalIdentity
    from security.customer_session import get_identity_verifier

    original = env.app.dependency_overrides[get_identity_verifier]
    class DifferentIssuer:
        async def verify(self, token, now):
            return ExternalIdentity("https://different.test.invalid", "subject-123")

    login(env)
    env.app.dependency_overrides[get_identity_verifier] = lambda: DifferentIssuer()
    try:
        response = env.client.post(f"{URL}/exchange", json={"id_token": "synthetic"})
        assert response.status_code == 401
        assert count(env, "customers") == 1 and count(env, "customer_identities") == 1
    finally:
        env.app.dependency_overrides[get_identity_verifier] = original


def test_exchange_idempotency_key_rejects_replay_without_extra_rows(env):
    body = {"id_token": token(),
            "idempotency_key": "idem_syntheticlogin01"}
    first = env.client.post(f"{URL}/exchange", json=body)
    second = env.client.post(f"{URL}/exchange", json=body)
    assert first.status_code == 200 and second.status_code == 409
    assert count(env, "customers") == 1 and count(env, "customer_identities") == 1
    assert count(env, "customer_sessions") == 1


def test_synthetic_phone_provider_uses_same_verified_issuer_subject_contract(env, monkeypatch):
    from repositories.customer_auth import identity_subject_key
    from tests.customer_auth_support import ISSUER

    monkeypatch.setattr(settings, "customer_auth_provider", "phone")
    provider = SyntheticPhoneOtpProvider()
    assert provider.exchange_otp("synthetic-phone-subject", "wrong") is None
    signed = provider.exchange_otp("synthetic-phone-subject", "000111")
    assert signed is not None
    first = env.client.post(f"{URL}/exchange", json={"id_token": signed}).json()["session_token"]
    second = env.client.post(f"{URL}/exchange", json={"id_token": signed}).json()["session_token"]
    assert first != second
    assert count(env, "customers") == 1 and count(env, "customer_identities") == 1
    assert env.sql("select provider, subject from customer_identities") == [
        ("phone", identity_subject_key(ISSUER, "synthetic-phone-subject"))]
