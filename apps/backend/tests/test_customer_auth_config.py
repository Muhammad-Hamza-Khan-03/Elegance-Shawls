"""M4 customer authentication, container-free: disabled by default and fail-closed config, strict request shape, own rate-limit bucket."""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from configuration.config import settings
from memory.principal import SESSION_HEADER, get_session_verifier
from routes.customer_auth_routes import router
from security import customer_session, rate_limit
from security.customer_session import customer_auth_ready, get_identity_verifier
from security.rate_limit import RateLimitMiddleware
from database.pg import get_pg_session

URL = "/v1/customer/auth"
GOOD = {"customer_auth_enabled": True, "customer_auth_provider": "google", "customer_auth_issuer": "https://idp.test.invalid",
        "customer_auth_audience": "aud", "customer_auth_jwks_url": "https://idp.test.invalid/jwks"}


def configure(monkeypatch, **over):
    for k, v in {**GOOD, **over}.items():
        monkeypatch.setattr(settings, k, v)
    get_identity_verifier.cache_clear()


def client(touch_db=False):
    app = FastAPI()
    app.include_router(router)

    async def no_db():
        if not touch_db:
            raise AssertionError("the database must not be touched")
        yield None

    app.dependency_overrides[get_pg_session] = no_db
    return TestClient(app, raise_server_exceptions=False)


def test_disabled_by_default():
    assert settings.customer_auth_enabled is False
    assert not customer_auth_ready() and get_identity_verifier() is None and get_session_verifier() is None


def test_disabled_exchange_is_404_and_session_routes_401_without_touching_the_database():
    c = client()
    assert c.post(f"{URL}/exchange", json={"id_token": "a.b.c"}).status_code == 404
    for path in ("logout", "logout-all"):
        assert c.post(f"{URL}/{path}", headers={SESSION_HEADER: "cs1.whatever"}).status_code == 401


@pytest.mark.parametrize("over", [
    {"customer_auth_enabled": False},
    {"customer_auth_provider": ""}, {"customer_auth_provider": "anon"}, {"customer_auth_provider": "facebook"},
    {"customer_auth_issuer": ""}, {"customer_auth_audience": ""}, {"customer_auth_jwks_url": ""},
    {"customer_auth_jwks_url": "http://idp.test.invalid/jwks"},
    {"customer_session_ttl_seconds": 0}, {"customer_session_max_active": 0},
])
def test_incomplete_or_unsafe_config_stays_disabled(monkeypatch, over):
    configure(monkeypatch, **over)
    assert not customer_auth_ready()
    assert get_identity_verifier() is None and get_session_verifier() is None
    assert client().post(f"{URL}/exchange", json={"id_token": "a.b.c"}).status_code == 404


def test_complete_config_enables_both_verifiers_without_any_network_call(monkeypatch):
    configure(monkeypatch)
    assert customer_auth_ready()
    assert get_identity_verifier() is get_identity_verifier()              # one cached JWKS per configuration
    assert get_session_verifier() is not None


@pytest.mark.parametrize("body", [
    {}, {"id_token": ""}, {"id_token": "x" * 4097}, {"id_token": 5}, {"id_token": "a.b.c", "customer_id": "00000000-0000-0000-0000-000000000001"},
    {"id_token": "a.b.c", "user_id": "x"}, {"customer_id": "x"},
])
def test_exchange_body_is_strict_and_never_accepts_a_customer_id(monkeypatch, body):
    configure(monkeypatch)
    assert client(touch_db=True).post(f"{URL}/exchange", json=body).status_code == 422


# ---- rate limit: its own, tighter bucket ---------------------------------------------------------
async def _ok(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


def _statuses(path, method, count, middleware):
    out = []

    async def send(message):
        if message["type"] == "http.response.start":
            out.append(message["status"])

    async def go():
        for _ in range(count):
            scope = {"type": "http", "method": method, "path": path, "headers": [], "query_string": b"",
                     "client": ("9.9.9.9", 1), "scheme": "http", "server": ("t", 80)}
            await middleware(scope, None, send)

    asyncio.run(go())
    return out


def test_customer_auth_has_its_own_limit_independent_of_admin_and_public(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_redis", lambda: None)
    monkeypatch.setattr(settings, "customer_auth_rate_limit_per_minute", 2)
    monkeypatch.setattr(settings, "admin_rate_limit_per_minute", 1000)
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1000)
    monkeypatch.setattr(settings, "events_rate_limit_per_minute", 1000)
    m = RateLimitMiddleware(_ok)
    assert _statuses(f"{URL}/exchange", "POST", 4, m) == [200, 200, 429, 429]
    assert _statuses(f"{URL}/logout", "POST", 1, m) == [429]                     # the whole prefix shares the bucket
    assert _statuses("/products/admin/x", "POST", 3, m) == [200, 200, 200]       # admin untouched
    assert _statuses("/v1/me/memory", "GET", 3, m) == [200, 200, 200]


def test_internal_token_does_not_exempt_customer_auth(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_redis", lambda: None)
    monkeypatch.setattr(settings, "customer_auth_rate_limit_per_minute", 1)
    monkeypatch.setattr(settings, "internal_api_token", "t" * 20)
    m = RateLimitMiddleware(_ok)
    out = []

    async def send(message):
        if message["type"] == "http.response.start":
            out.append(message["status"])

    async def go():
        for _ in range(2):
            scope = {"type": "http", "method": "POST", "path": f"{URL}/exchange", "headers": [(b"x-internal-api-token", b"t" * 20)],
                     "query_string": b"", "client": ("8.8.8.8", 1), "scheme": "http", "server": ("t", 80)}
            await m(scope, None, send)

    asyncio.run(go())
    assert out == [200, 429]
