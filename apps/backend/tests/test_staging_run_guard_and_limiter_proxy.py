"""Seed/backfill guard, Dockerfile defaults, trusted-proxy keying and idle-key eviction. Hermetic: no network, no database."""
import asyncio
from pathlib import Path

import pytest
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from configuration.config import settings
from ingestion.staging_guard import StagingGuardError, assert_staging_run
from security import rate_limit
from security.rate_limit import RateLimitMiddleware

STAGING_DB = "postgresql+asyncpg://u:p@h/elegance_staging"
GOOD = {"ENVIRONMENT": "staging", "RUN_STAGING_SEED": "true", "DATABASE_URL": STAGING_DB}


def test_guard_accepts_only_the_full_opt_in():
    assert_staging_run("RUN_STAGING_SEED", GOOD)


@pytest.mark.parametrize("change", [
    {"ENVIRONMENT": ""}, {"ENVIRONMENT": "production"}, {"ENVIRONMENT": "stagin"}, {"ENVIRONMENT": "development"},
    {"RUN_STAGING_SEED": ""}, {"RUN_STAGING_SEED": "false"},
    {"DATABASE_URL": ""}, {"DATABASE_URL": "postgresql+asyncpg://u:p@h/elegance_prod"}, {"DATABASE_URL": "postgresql+asyncpg://u:p@h/elegance"},
])
def test_guard_refuses_unset_unknown_or_unopted(change):
    with pytest.raises(StagingGuardError):
        assert_staging_run("RUN_STAGING_SEED", {**GOOD, **change})


def test_guard_refuses_when_variables_are_absent():
    with pytest.raises(StagingGuardError):
        assert_staging_run("RUN_STAGING_SEED", {})


def test_dockerfile_defaults_are_production_safe():
    text = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    for line in ("ENVIRONMENT=production", "RUN_STAGING_SEED=false", "RUN_E5_BACKFILL_ON_STARTUP=false",
                 "EMBEDDING_ENABLED=false", "LOCAL_SEMANTIC_SEARCH_ENABLED=false"):
        assert line in text
    assert "ENVIRONMENT=staging" not in text and "embedding_backfill.py --require-staging" in text


async def _ok(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


def _statuses(app, hits, *, peer, forwarded=None, path="/products/", method="GET"):
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []

    async def go():
        out = []
        for _ in range(hits):
            async def send(message):
                if message["type"] == "http.response.start":
                    out.append(message["status"])

            scope = {"type": "http", "method": method, "path": path, "headers": headers, "query_string": b"",
                     "client": (peer, 1), "scheme": "http", "server": ("t", 80)}
            await app(scope, None, send)
        return out

    return asyncio.run(go())


@pytest.fixture
def limits(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_redis", lambda: None)
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1)
    monkeypatch.setattr(settings, "admin_rate_limit_per_minute", 1)
    monkeypatch.setattr(settings, "events_rate_limit_per_minute", 1)


def _proxied(trusted):
    return ProxyHeadersMiddleware(RateLimitMiddleware(_ok), trusted_hosts=trusted)


def _two_clients(app, peer, **kw):
    """Two different forwarded clients, one request each, through one app instance."""
    return [_statuses(app, 1, peer=peer, forwarded=ip, **kw)[0] for ip in ("9.9.9.1", "9.9.9.2")]


def test_trusted_proxy_keys_each_forwarded_client_separately(limits):
    assert _two_clients(_proxied("10.0.0.1"), "10.0.0.1") == [200, 200]


def test_untrusted_proxy_cannot_choose_its_own_address(limits):
    app = _proxied("10.0.0.1")
    assert _two_clients(app, "6.6.6.6") == [200, 429]  # header ignored: both keyed by the peer


def test_wildcard_trusts_any_peer_so_forwarded_header_picks_the_key(limits):
    assert _two_clients(_proxied("*"), "6.6.6.6") == [200, 200]  # why `*` is only safe behind a proxy that overwrites the header


@pytest.mark.parametrize("path,method", [("/products/admin/x", "GET"), ("/v1/events", "POST"), ("/products/", "POST")])
def test_admin_and_events_stay_limited_per_forwarded_client(limits, path, method):
    app = _proxied("10.0.0.1")
    assert _statuses(app, 2, peer="10.0.0.1", forwarded="9.9.9.1", path=path, method=method) == [200, 429]
    assert _statuses(app, 1, peer="10.0.0.1", forwarded="9.9.9.2", path=path, method=method) == [200]


def test_idle_keys_are_swept_and_active_keys_keep_their_count(limits, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(rate_limit, "monotonic", lambda: now[0])
    mw = RateLimitMiddleware(_ok)
    for i in range(500):
        assert mw._hit_local(f"c{i}:public", 5)
    assert mw._hit_local("busy:public", 2) and len(mw.requests) == 501
    now[0] += 30  # inside the window: the sweep has not run, nothing is dropped, busy still counts
    assert mw._hit_local("busy:public", 2) and not mw._hit_local("busy:public", 2) and len(mw.requests) == 501
    now[0] += 31  # past the first sweep: idle keys go, "busy" (last hit 31s ago) stays with its count
    assert mw._hit_local("busy:public", 2)  # old hits aged out of the window, so a fresh one is allowed
    assert len(mw.requests) == 1 and "busy:public" in mw.requests


def test_key_count_stays_bounded_under_a_stream_of_distinct_clients(limits, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(rate_limit, "monotonic", lambda: now[0])
    mw = RateLimitMiddleware(_ok)
    peak = 0
    for second in range(600):  # 10 minutes, 20 new clients per second
        now[0] = float(second)
        for j in range(20):
            mw._hit_local(f"c{second}-{j}", 5)
        peak = max(peak, len(mw.requests))
    assert peak <= 20 * 121  # at most ~two windows of clients, never all 12000


def test_local_key_map_obeys_configured_bound(limits, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(rate_limit, "monotonic", lambda: now[0])
    monkeypatch.setattr(settings, "local_rate_limit_max_keys", 3)
    mw = RateLimitMiddleware(_ok)

    for key in ("old", "middle", "new"):
        assert mw._hit_local(key, 5)
        now[0] += 1
    assert len(mw.requests) == 3
    assert mw._hit_local("latest", 5)
    assert len(mw.requests) == 3
    assert "old" not in mw.requests
