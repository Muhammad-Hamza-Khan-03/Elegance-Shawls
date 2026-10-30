import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from configuration.config import settings
from llm import model_discovery as md
from main import create_app


class ClientFactory:
    def __init__(self, handler):
        self.handler = handler
        self.calls = 0

    def __call__(self, **kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle), **kwargs)

    async def _handle(self, request):
        self.calls += 1
        return await self.handler(request)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    md._memory.clear()
    md._background.clear()
    md._inflight.clear()
    monkeypatch.setattr(md, "get_redis", lambda: None)
    monkeypatch.setattr(settings, "llm_discovery_max_attempts", 3)
    monkeypatch.setattr(settings, "llm_discovery_retry_after_cap_seconds", 0)
    monkeypatch.setattr(settings, "llm_discovery_fresh_ttl_seconds", 1)
    monkeypatch.setattr(settings, "llm_discovery_stale_ceiling_seconds", 3600)
    monkeypatch.setenv("GROQ_API_KEY", "groq-distinctive-fake-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-distinctive-fake-key")


@pytest.mark.asyncio
async def test_groq_normalizes_allowlisted_metadata_and_secret_is_not_cached():
    async def handler(request):
        assert request.headers["authorization"] == "Bearer groq-distinctive-fake-key"
        return httpx.Response(200, json={"data": [{"id": "llama-3", "active": True, "context_window": 8192, "max_completion_tokens": 1024, "secret": "drop"}]})
    client = ClientFactory(handler)
    service = md.ModelDiscovery(client)
    assert (await service.refresh("groq")) == "ok"
    result = await service.read("groq")
    assert result["models"][0]["model_id"] == "groq/llama-3"
    assert "secret" not in json.dumps(result)
    assert "groq-distinctive-fake-key" not in json.dumps(result)


@pytest.mark.asyncio
async def test_gemini_pagination_prefix_strip_and_generation_filter():
    async def handler(request):
        if request.url.params.get("pageToken"):
            return httpx.Response(200, json={"models": [{"name": "models/gemini-2", "displayName": "Two", "version": "2", "inputTokenLimit": 8, "outputTokenLimit": 4, "supportedGenerationMethods": ["generateContent"]}]})
        return httpx.Response(200, json={"models": [{"name": "models/embed", "supportedGenerationMethods": ["embedContent"]}], "nextPageToken": "next"})
    client = ClientFactory(handler)
    service = md.ModelDiscovery(client)
    await service.refresh("gemini")
    result = await service.read("gemini")
    assert [m["model_id"] for m in result["models"]] == ["gemini/gemini-2"]
    assert client.calls == 2


@pytest.mark.asyncio
async def test_401_is_not_retried_and_failed_refresh_keeps_last_known_good(monkeypatch):
    calls = 0
    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(401)
    client = ClientFactory(handler)
    service = md.ModelDiscovery(client)
    assert await service.refresh("groq") == "error"
    assert calls == 1
    md._memory[md.CACHE_KEYS["groq"]] = json.dumps({"models": [{"provider": "groq", "model_id": "groq/old", "status": "available", "generation_methods": ["chat"]}], "refreshed_at": md._now(), "last_ok_at": md._now(), "state": "ok", "error_kind": None})
    assert await service.refresh("groq") == "error"
    assert (await service.read("groq"))["models"][0]["model_id"] == "groq/old"


@pytest.mark.asyncio
async def test_timeout_and_5xx_are_bounded():
    calls = 0
    async def handler(request):
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"data": []})
    client = ClientFactory(handler)
    service = md.ModelDiscovery(client)
    assert await service.refresh("groq") == "ok"
    assert calls == 3


@pytest.mark.asyncio
async def test_concurrent_refreshes_share_one_provider_request():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(request):
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"data": []})

    client = ClientFactory(handler)
    service = md.ModelDiscovery(client)
    first = asyncio.create_task(service.refresh("groq"))
    await entered.wait()
    second = asyncio.create_task(service.refresh("groq"))
    release.set()

    assert await asyncio.gather(first, second) == ["ok", "ok"]
    assert client.calls == 1


@pytest.mark.asyncio
async def test_admin_visibility_and_auth(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "admin-test-key")
    client = TestClient(create_app())
    assert client.get("/v1/llm/models").status_code in (401, 403)
    response = client.get("/v1/llm/models", headers={"X-Admin-Key": "admin-test-key"})
    assert response.status_code == 200
    assert "models" in response.json()


def test_scheduled_refresh_is_on_existing_arq_worker():
    from workers.settings import WorkerSettings
    names = {getattr(job, "__name__", "") for job in WorkerSettings.functions}
    assert "refresh_llm_models_job" in names
