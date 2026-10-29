"""Eval embedding provider contract: allowlist gates, Gemini mapping, Groq fail-closed. Mocked transport, no network."""
import json
import logging
import socket

import httpx
import pytest

from embeddings.config import ALLOWLIST_VAR, EvalConfig, load_eval_config, parse_allowlist
from embeddings.provider import (
    ConfigError,
    EmbeddingLimits,
    EmbeddingProvider,
    InputError,
    MalformedResponseError,
    ProviderRequestError,
    UnsupportedProviderError,
)
from embeddings.providers import build_provider

KEY = "sk-secret-key-123"
TEXT = "synthetic-shawl-text-xyz"
ENV = {
    ALLOWLIST_VAR: "gemini/gemini-embedding-001,groq/some-model",
    "EMBEDDING_EVAL_GEMINI_API_KEY": KEY,
    "EMBEDDING_EVAL_GROQ_API_KEY": "groq-secret",
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*_, **__):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def gemini(handler, dim=3, limits=None):
    cfg = load_eval_config("gemini", "gemini-embedding-001", ENV)
    return build_provider(cfg, dim, limits, transport=httpx.MockTransport(handler))


def ok(n=1, dim=3, **extra):
    return httpx.Response(200, json={"embeddings": [{"values": [0.1] * dim} for _ in range(n)], **extra},
                          headers={"x-request-id": "req-1"})


# --- allowlist / credential gates -------------------------------------------------------------------------------

def test_allowlist_parses_and_resolves():
    assert parse_allowlist("gemini/a, groq/b") == {("gemini", "a"), ("groq", "b")}
    cfg = load_eval_config("gemini", "gemini-embedding-001", ENV)
    assert (cfg.provider, cfg.model, cfg.api_key) == ("gemini", "gemini-embedding-001", KEY)
    assert KEY not in repr(cfg)


@pytest.mark.parametrize("raw", [None, "", "  ", "gemini", "gemini/", "/m", "openai/m", "gemini/a,,groq/b",
                                 "gemini/a,gemini/a", "gemini/a/b", "gemini/a b", "gemini/../x", "gemini/*"])
def test_bad_allowlists_rejected(raw):
    with pytest.raises(ConfigError):
        parse_allowlist(raw)


@pytest.mark.parametrize("provider,model", [("gemini", "other"), ("groq", "gemini-embedding-001"),
                                            ("openai", "gemini-embedding-001"), ("", ""), ("gemini", "")])
def test_undeclared_combinations_rejected(provider, model):
    with pytest.raises(ConfigError):
        load_eval_config(provider, model, ENV)


def test_missing_credentials_rejected():
    for key in ("EMBEDDING_EVAL_GEMINI_API_KEY",):
        for value in (None, "", "  "):
            env = {k: v for k, v in ENV.items() if k != key}
            if value is not None:
                env[key] = value
            with pytest.raises(ConfigError):
                load_eval_config("gemini", "gemini-embedding-001", env)


def test_chat_llm_config_is_not_consulted():
    env = {ALLOWLIST_VAR: "gemini/m", "GEMINI_API_KEY": KEY, "LLM_API_KEY": KEY, "OPENAI_API_KEY": KEY}
    with pytest.raises(ConfigError):
        load_eval_config("gemini", "m", env)


# --- groq fail-closed -------------------------------------------------------------------------------------------

def test_groq_fails_closed_without_any_request():
    cfg = load_eval_config("groq", "some-model", ENV)

    def boom(request):
        raise AssertionError("groq must not send anything")

    with pytest.raises(UnsupportedProviderError):
        build_provider(cfg, 3, transport=httpx.MockTransport(boom))


def test_unknown_provider_has_no_fallback():
    with pytest.raises(UnsupportedProviderError):
        build_provider(EvalConfig("openai", "m", KEY), 3)


# --- gemini request / response mapping --------------------------------------------------------------------------

def test_gemini_request_shape_and_result_mapping():
    seen = []

    def handler(request):
        seen.append(request)
        return ok(2, usageMetadata={"totalTokenCount": 7, "bad": True, "s": "x"})

    p = gemini(handler)
    assert isinstance(p, EmbeddingProvider)
    result = p.embed(["a", "b"])
    (req,) = seen
    assert req.method == "POST"
    assert str(req.url) == "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"
    assert req.headers["x-goog-api-key"] == KEY and KEY not in str(req.url)
    assert json.loads(req.content) == {"model": "models/gemini-embedding-001", "requests": [
        {"model": "models/gemini-embedding-001", "content": {"parts": [{"text": t}]}, "outputDimensionality": 3}
        for t in ("a", "b")]}
    assert result.vectors == [[0.1] * 3] * 2
    assert (result.provider, result.model, result.dimension, result.item_count) == (
        "gemini", "gemini-embedding-001", 3, 2)
    assert result.usage == {"totalTokenCount": 7}
    assert result.request == {"request_id": "req-1", "attempts": 1}


def test_gemini_timeout_is_passed_to_transport():
    seen = []

    def handler(request):
        seen.append(request.extensions["timeout"])
        return ok()

    gemini(handler, limits=EmbeddingLimits(timeout_s=5)).embed(["a"])
    assert seen[0]["read"] == 5 and seen[0]["connect"] == 5


@pytest.mark.parametrize("response", [
    httpx.Response(200, content=b"not json"),
    httpx.Response(200, json=[]),
    httpx.Response(200, json={}),
    httpx.Response(200, json={"embeddings": "x"}),
    httpx.Response(200, json={"embeddings": [{}]}),
    httpx.Response(200, json={"embeddings": [{"values": [0.1, 0.2, 0.3]}] * 2}),
    httpx.Response(200, json={"embeddings": [{"values": [0.1, 0.2]}]}),
    httpx.Response(200, json={"embeddings": [{"values": [0.1, True, 0.3]}]}),
])
def test_gemini_malformed_responses_rejected(response):
    with pytest.raises(MalformedResponseError):
        gemini(lambda r: response).embed(["a"])


def test_error_status_is_typed_and_not_retried_when_permanent():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, text=f"bad key {KEY} {TEXT}")

    with pytest.raises(ProviderRequestError) as exc:
        gemini(handler).embed([TEXT])
    assert exc.value.status == 401 and len(calls) == 1
    assert KEY not in str(exc.value) and TEXT not in str(exc.value)


# --- bounded retry ----------------------------------------------------------------------------------------------

def test_one_transport_retry_then_success():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("boom " + KEY)
        return ok()

    result = gemini(handler).embed(["a"])
    assert len(calls) == 2 and result.request["attempts"] == 2


def test_retry_is_bounded_to_one():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)

    with pytest.raises(ProviderRequestError) as exc:
        gemini(handler).embed(["a"])
    assert len(calls) == 2 and exc.value.status == 503


def test_zero_retries_configured():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("t")

    with pytest.raises(ProviderRequestError):
        gemini(handler, limits=EmbeddingLimits(max_retries=0)).embed(["a"])
    assert len(calls) == 1


# --- limits / no fallback / no leaks ----------------------------------------------------------------------------

@pytest.mark.parametrize("kwargs", [{"max_batch": 17}, {"max_batch": 0}, {"max_retries": 2}, {"timeout_s": 0},
                                    {"timeout_s": 61}, {"max_chars": 0}])
def test_limits_cannot_exceed_bounds(kwargs):
    with pytest.raises(ConfigError):
        EmbeddingLimits(**kwargs)


def test_batch_and_length_limits_checked_before_any_request():
    def boom(request):
        raise AssertionError("no request expected")

    p = gemini(boom, limits=EmbeddingLimits(max_chars=10))
    for texts in (["a"] * 17, [], ["x" * 11], [""], ["  "], [None], "abc"):
        with pytest.raises(InputError):
            p.embed(texts)
    assert gemini(lambda r: ok(16)).embed(["a"] * 16).item_count == 16


def test_no_fallback_on_failure_and_single_endpoint():
    urls = []

    def handler(request):
        urls.append(request.url.host + request.url.path)
        return httpx.Response(500)

    with pytest.raises(ProviderRequestError):
        gemini(handler).embed(["a"])
    assert set(urls) == {"generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"}


def test_nothing_logged_and_errors_redacted(caplog, capsys):
    caplog.set_level(logging.DEBUG)
    body = json.dumps({"embeddings": [{"values": [0.123456]}]})

    def handler(request):
        return httpx.Response(200, text=body[:-3])  # truncated -> malformed

    with pytest.raises(MalformedResponseError) as exc:
        gemini(handler, dim=1).embed([TEXT])
    out = capsys.readouterr()
    haystack = caplog.text + out.out + out.err + repr(exc.value) + str(exc.value)
    for secret in (KEY, TEXT, "0.123456", '"values"'):
        assert secret not in haystack
    assert exc.value.__cause__ is None and exc.value.__suppress_context__
