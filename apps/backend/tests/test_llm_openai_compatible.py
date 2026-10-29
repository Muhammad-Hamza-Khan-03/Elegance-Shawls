import asyncio
import json
import logging

import httpx
import pytest

from configuration.config import settings
from llm import gateway as gw
from llm.gateway import AllProvidersFailedError, BudgetTracker, LLMGateway
from llm.openai_compatible import ProviderError, openai_compatible_completion, supports

MESSAGES = [{"role": "user", "content": "private customer text"}]
FAKE_KEY = "test-key-not-real-0000"


def transport(handler, seen=None):
    def wrapped(request: httpx.Request):
        if seen is not None:
            seen.append(request)
        return handler(request)

    return httpx.MockTransport(wrapped)


def ok(content="hello", usage=None):
    body = {"choices": [{"message": {"content": content}}], "usage": usage or {"prompt_tokens": 7, "completion_tokens": 2}}
    return lambda request: httpx.Response(200, json=body)


def call(model, handler, seen=None):
    return asyncio.run(openai_compatible_completion(model, MESSAGES, 2.0, transport=transport(handler, seen)))


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    for name in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setenv(name, FAKE_KEY)
    for name in ("GROQ_BASE_URL", "OLLAMA_BASE_URL", "GEMINI_BASE_URL", "OPENROUTER_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings, "llm_price_per_million_input_usd", 0.0)
    monkeypatch.setattr(settings, "llm_price_per_million_output_usd", 0.0)


@pytest.mark.parametrize("model,url,upstream", [
    ("groq/openai/gpt-oss-120b", "https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b"),
    ("gemini/gemini-2.5-flash", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.5-flash"),
    ("openrouter/meta-llama/llama-3.3-70b:free", "https://openrouter.ai/api/v1/chat/completions", "meta-llama/llama-3.3-70b:free"),
    ("ollama/qwen2.5", "http://localhost:11434/v1/chat/completions", "qwen2.5"),
])
def test_request_targets_the_provider_with_the_upstream_model_name(model, url, upstream):
    seen = []
    reply = call(model, ok(), seen)
    [request] = seen
    assert str(request.url) == url and json.loads(request.content)["model"] == upstream
    assert json.loads(request.content)["stream"] is False
    assert (reply.text, reply.input_tokens, reply.output_tokens) == ("hello", 7, 2)


def test_key_goes_only_in_the_authorization_header_and_ollama_sends_none():
    seen = []
    call("groq/x", ok(), seen)
    assert seen[0].headers["authorization"] == f"Bearer {FAKE_KEY}" and FAKE_KEY not in str(seen[0].url) + seen[0].content.decode()
    seen.clear()
    call("ollama/x", ok(), seen)
    assert "authorization" not in seen[0].headers


def test_missing_key_names_the_variable_and_makes_no_request(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    seen = []
    with pytest.raises(ProviderError, match="GROQ_API_KEY is not set"):
        call("groq/x", ok(), seen)
    assert seen == []


def test_base_url_can_point_at_a_self_hosted_gateway(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.internal:11434/v1/")
    seen = []
    call("ollama/x", ok(), seen)
    assert str(seen[0].url) == "http://ollama.internal:11434/v1/chat/completions"


def test_http_errors_report_status_only_never_the_body_or_key():
    handler = lambda request: httpx.Response(429, text=f"rate limited for private customer text {FAKE_KEY}")
    with pytest.raises(ProviderError) as error:
        call("groq/x", handler)
    assert str(error.value) == "groq returned HTTP 429"


def test_openrouter_reported_cost_wins_and_price_table_covers_the_rest(monkeypatch):
    assert call("openrouter/x", ok(usage={"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0123})).cost_usd == 0.0123
    monkeypatch.setattr(settings, "llm_price_per_million_input_usd", 2.0)
    monkeypatch.setattr(settings, "llm_price_per_million_output_usd", 10.0)
    assert call("groq/x", ok(usage={"prompt_tokens": 1000, "completion_tokens": 500})).cost_usd == pytest.approx(0.007)


def test_missing_usage_and_empty_content_are_tolerated():
    reply = call("groq/x", lambda r: httpx.Response(200, json={"choices": [{"message": {"content": None}}]}))
    assert (reply.text, reply.input_tokens, reply.cost_usd) == ("", 0, 0.0)


def test_supports_only_the_built_in_providers():
    assert supports("groq/x") and supports("OLLAMA/x") and not supports("mistral/x") and not supports("fake/x")


# --- through the gateway --------------------------------------------------------------------------
def gateway_with(handler, seen=None):
    async def completion(model, messages, timeout):
        return await openai_compatible_completion(model, messages, timeout, transport=transport(handler, seen))

    return LLMGateway(completion=completion, budget=BudgetTracker(1, 10, 0.8))


def test_first_provider_failing_falls_back_to_the_next_and_cost_is_recorded(monkeypatch):
    monkeypatch.setattr(settings, "llm_chain_default", "groq/a,gemini/b")
    monkeypatch.setattr(settings, "llm_timeout_seconds", 2.0)
    monkeypatch.setattr(settings, "llm_price_per_million_input_usd", 1000.0)

    def handler(request):
        return httpx.Response(503) if "groq" in str(request.url) else ok()(request)

    result = asyncio.run(gateway_with(handler).complete(MESSAGES))
    assert (result.model, result.attempts, result.fallback_used) == ("gemini/b", 2, True)
    assert result.cost_usd == pytest.approx(0.007)


def test_all_providers_failing_raises_so_callers_can_degrade(monkeypatch):
    monkeypatch.setattr(settings, "llm_chain_default", "groq/a,gemini/b")
    with pytest.raises(AllProvidersFailedError):
        asyncio.run(gateway_with(lambda r: httpx.Response(500)).complete(MESSAGES))


def test_personal_data_is_never_sent_to_free_tier_providers_even_when_misconfigured(monkeypatch):
    seen = []
    monkeypatch.setattr(settings, "llm_production_chain", "groq/a,gemini/b,ollama/private")
    asyncio.run(gateway_with(ok(), seen).complete(MESSAGES, personal=True))
    assert [str(r.url) for r in seen] == ["http://localhost:11434/v1/chat/completions"]   # self-hosted only


def test_prompts_and_keys_never_reach_the_logs(monkeypatch, caplog):
    monkeypatch.setattr(settings, "llm_chain_default", "groq/a,gemini/b")
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(AllProvidersFailedError):
            asyncio.run(gateway_with(lambda r: httpx.Response(401, text="bad key " + FAKE_KEY)).complete(MESSAGES))
    logged = caplog.text
    assert FAKE_KEY not in logged and "private customer text" not in logged


def test_default_route_sends_builtin_providers_to_the_adapter_and_others_to_litellm(monkeypatch):
    calls = []

    async def adapter(model, messages, timeout):
        calls.append(("adapter", model))
        return None

    async def litellm_path(model, messages, timeout):
        calls.append(("litellm", model))
        return None

    monkeypatch.setattr(gw, "openai_compatible_completion", adapter)
    monkeypatch.setattr(gw, "_litellm_completion", litellm_path)
    asyncio.run(gw._route_completion("groq/x", MESSAGES, 1))
    asyncio.run(gw._route_completion("mistral/x", MESSAGES, 1))
    assert calls == [("adapter", "groq/x"), ("litellm", "mistral/x")]
