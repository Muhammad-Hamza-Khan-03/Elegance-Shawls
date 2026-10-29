import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import main
from configuration.config import settings
from database.pg import get_pg_session
from events import retention
from events.session import mint_session_token, verify_session_token

KEY = "test-signing-key-for-events-only"


class FakeSession:
    def __init__(self):
        self.rows, self.commits = [], 0

    def add_all(self, rows):
        self.rows.extend(rows)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(settings, "session_signing_key", KEY)
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1000)
    monkeypatch.setattr(settings, "events_rate_limit_per_minute", 1000)
    fake = FakeSession()
    app = main.create_app()

    async def override():
        yield fake

    app.dependency_overrides[get_pg_session] = override
    client = TestClient(app)
    client.fake = fake
    return client


def batch(*events):
    return {"events": list(events)}


VIEW = {"type": "view", "payload": {"product_id": "p1", "slug": "classic-wool-shawl"}}


def test_valid_batch_is_stored_with_a_signed_session(api):
    response = api.post("/v1/events", json=batch(VIEW, {"type": "search", "payload": {"q": "brown stole", "category": "stoles"}}))
    assert response.status_code == 202 and response.json()["accepted"] == 2
    token = response.json()["session_token"]
    assert verify_session_token(token) == api.fake.rows[0].session_id
    assert [r.type for r in api.fake.rows] == ["view", "search"]
    assert all(r.session_id == api.fake.rows[0].session_id for r in api.fake.rows)
    assert api.fake.commits == 1


def test_session_cookie_is_http_only_and_signed(api):
    cookie = api.post("/v1/events", json=batch(VIEW)).headers["set-cookie"]
    assert "es_sid=v1." in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie


def test_existing_valid_session_is_kept_and_tampered_one_is_replaced(api):
    token = mint_session_token()
    kept = api.post("/v1/events", json=batch(VIEW), headers={"X-Session-Token": token}).json()["session_token"]
    assert kept == token
    forged = token[:-1] + ("0" if token[-1] != "0" else "1")
    replaced = api.post("/v1/events", json=batch(VIEW), headers={"X-Session-Token": forged}).json()["session_token"]
    assert replaced != forged and verify_session_token(replaced)


def test_customer_id_stays_null(api):
    api.post("/v1/events", json=batch(VIEW))
    assert all(r.customer_id is None for r in api.fake.rows)


@pytest.mark.parametrize("body", [
    {"events": []},
    {"events": [{"type": "handoff", "payload": {}}]},          # server-originated types are rejected
    {"events": [{"type": "view", "payload": {"a": {"nested": 1}}}]},
    {"events": [{"type": "view", "payload": {"a": "x" * 201}}]},
    {"events": [{"type": "view", "payload": {f"k{i}": 1 for i in range(11)}}]},
    {"nope": 1},
])
def test_invalid_events_are_rejected(api, body):
    assert api.post("/v1/events", json=body).status_code == 422
    assert api.fake.rows == []


def test_batch_size_is_capped(api):
    assert api.post("/v1/events", json=batch(*[VIEW] * settings.events_max_batch)).status_code == 202
    assert api.post("/v1/events", json=batch(*[VIEW] * (settings.events_max_batch + 1))).status_code == 422


def test_oversized_body_is_rejected(api, monkeypatch):
    big = batch(*[{"type": "search", "payload": {"q": "y" * 200}}] * 20)
    assert api.post("/v1/events", json=big).status_code == 202  # ~4.6 KB is under the default cap
    monkeypatch.setattr(settings, "events_max_body_bytes", 1000)
    assert api.post("/v1/events", json=big).status_code == 413
    # No Content-Length: the streamed size is still enforced.
    chunks = (b'{"events":[{"type":"view","payload":{"a":"' + b"z" * 150 + b'"}}' + b"," if i else b"" for i in range(30))
    assert api.post("/v1/events", content=chunks, headers={"content-type": "application/json"}).status_code == 413


def test_contact_details_in_search_text_are_scrubbed(api):
    api.post("/v1/events", json=batch({"type": "search", "payload": {"q": "call me 0300 1234567 or a@b.com"}}))
    stored = api.fake.rows[0].payload["q"]
    assert "1234567" not in stored and "a@b.com" not in stored


def test_disabled_without_signing_key(api, monkeypatch):
    monkeypatch.setattr(settings, "session_signing_key", "")
    assert api.post("/v1/events", json=batch(VIEW)).status_code == 503


def test_postgres_outage_is_503_not_a_crash(monkeypatch):
    monkeypatch.setattr(settings, "session_signing_key", KEY)
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1000)
    assert TestClient(main.create_app()).post("/v1/events", json=batch(VIEW)).status_code == 503


def test_events_have_their_own_rate_limit_and_are_never_exempt(monkeypatch):
    monkeypatch.setattr(settings, "session_signing_key", KEY)
    monkeypatch.setattr(settings, "events_rate_limit_per_minute", 2)
    monkeypatch.setattr(settings, "internal_api_token", "internal-token-fixture")
    client = TestClient(main.create_app())
    headers = {"X-Internal-API-Token": "internal-token-fixture"}
    codes = [client.post("/v1/events", json=batch(VIEW), headers=headers).status_code for _ in range(3)]
    assert codes[2] == 429
    assert client.get("/health/").status_code == 200  # other traffic unaffected


def test_session_tokens_need_a_signing_key(monkeypatch):
    monkeypatch.setattr(settings, "session_signing_key", KEY)
    token = mint_session_token()
    monkeypatch.setattr(settings, "session_signing_key", "")
    assert verify_session_token(token) is None
    assert verify_session_token(None) is None and verify_session_token("garbage") is None


def test_retention_deletes_only_events_older_than_the_window():
    class Result:
        rowcount = 3

    class Recorder:
        statement = None

        async def execute(self, statement):
            self.statement = statement
            return Result()

        async def commit(self):
            pass

    session = Recorder()
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    assert asyncio.run(retention.purge_expired_events(session, months=18, now=now)) == 3
    assert str(session.statement.compile(compile_kwargs={"literal_binds": True})).count("events.created_at <") == 1
    assert (now - timedelta(days=30 * 18)).date().isoformat() in str(
        session.statement.compile(compile_kwargs={"literal_binds": True}))
