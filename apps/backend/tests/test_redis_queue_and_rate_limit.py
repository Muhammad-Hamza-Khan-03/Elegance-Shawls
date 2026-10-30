import asyncio

import pytest
from fakeredis import FakeAsyncRedis
from fastapi.testclient import TestClient

import main
from configuration.config import settings
from security import rate_limit
from security.rate_limit import RateLimitMiddleware
from workers import queues
from workers.queues import QueueUnavailable


async def _ok(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def _call(middleware) -> int:
    status = []

    async def send(message):
        if message["type"] == "http.response.start":
            status.append(message["status"])

    scope = {"type": "http", "method": "GET", "path": "/products/", "headers": [],
             "query_string": b"", "client": ("1.2.3.4", 1), "scheme": "http", "server": ("t", 80)}
    await middleware(scope, None, send)
    return status[0]


def _sequence(*middlewares) -> list[int]:
    """One event loop for the whole sequence, as in a running server."""
    async def go():
        return [await _call(m) for m in middlewares]

    return asyncio.run(go())


def test_limit_is_shared_across_two_replicas(monkeypatch):
    redis = FakeAsyncRedis()
    monkeypatch.setattr(rate_limit, "get_redis", lambda: redis)
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 2)
    replica_a, replica_b = RateLimitMiddleware(_ok), RateLimitMiddleware(_ok)

    assert _sequence(replica_a, replica_b, replica_a, replica_b) == [200, 200, 429, 429]


def test_falls_back_to_in_process_limit_when_redis_fails(monkeypatch):
    class BrokenRedis:
        async def incr(self, *_):
            raise ConnectionError("down")

    monkeypatch.setattr(rate_limit, "get_redis", lambda: BrokenRedis())
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1)
    middleware = RateLimitMiddleware(_ok)
    assert _sequence(middleware, middleware) == [200, 429]


def test_no_redis_uses_in_process_limit(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_redis", lambda: None)
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1)
    middleware = RateLimitMiddleware(_ok)
    assert _sequence(middleware, middleware) == [200, 429]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "test-key")
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1000)
    monkeypatch.setattr(settings, "admin_rate_limit_per_minute", 1000)
    return TestClient(main.create_app())


def test_job_routes_require_admin_key(client):
    assert client.post("/v1/admin/jobs/sample", json={"value": "x"}).status_code in (401, 403)


def test_job_routes_return_503_without_redis(client, monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "")
    response = client.post("/v1/admin/jobs/sample", json={"value": "x"}, headers={"X-Admin-Key": "test-key"})
    assert response.status_code == 503
    assert client.get("/v1/admin/jobs/abc", headers={"X-Admin-Key": "test-key"}).status_code == 503


def test_job_enqueue_returns_job_id(client, monkeypatch):
    async def fake_enqueue(function, *args, **kwargs):
        assert (function, args) == ("sample_job", ("hello", 0))
        return "job-1"

    from routes import job_routes
    monkeypatch.setattr(job_routes, "enqueue", fake_enqueue)
    response = client.post("/v1/admin/jobs/sample", json={"value": "hello"}, headers={"X-Admin-Key": "test-key"})
    assert (response.status_code, response.json()) == (202, {"job_id": "job-1"})


def test_job_payload_is_bounded(client):
    response = client.post("/v1/admin/jobs/sample", json={"value": "x" * 201}, headers={"X-Admin-Key": "test-key"})
    assert response.status_code == 422


def test_queue_names_are_distinct_and_namespaced():
    assert len(set(queues.QUEUES.values())) == len(queues.QUEUES)
    assert all(name.startswith("elegance:ai:") for name in queues.QUEUES.values())


def test_enqueue_raises_queue_unavailable_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "")
    with pytest.raises(QueueUnavailable):
        asyncio.run(queues.enqueue("sample_job", "x"))
