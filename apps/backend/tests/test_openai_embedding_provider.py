"""OpenAI comparison adapter: allowlist, key isolation, request mapping, validation, bounded retries, redaction.
Mocked transport only; any socket use fails the test."""
import json
import logging
import socket

import httpx
import pytest

from embeddings.config import ALLOWLIST_VAR, load_eval_config, parse_allowlist
from embeddings.provider import (
    ConfigError,
    EmbeddingLimits,
    InputError,
    MalformedResponseError,
    ProviderRequestError,
)
from embeddings.providers import build_provider

KEY = "sk-openai-secret-123"
TEXT = "synthetic-shawl-text-xyz"
MODEL = "text-embedding-3-small"
ENV = {ALLOWLIST_VAR: f"openai/{MODEL}", "OPENAI_API_KEY": KEY}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*_, **__):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def vec(i, dim=768):
    return [float(i)] * dim


def ok(request, dim=768, shuffle=False):
    n = len(json.loads(request.content)["input"])
    data = [item(i, vec(i, dim)) for i in range(n)]
    return httpx.Response(200, json={"object": "list", "model": MODEL, "data": data[::-1] if shuffle else data,
                                     "usage": {"prompt_tokens": 7, "total_tokens": 7}}, headers={"x-request-id": "req-1"})


def item(index, embedding, **over):
    return {"object": "embedding", "index": index, "embedding": embedding} | over


def payload(*items, **top):
    return {"object": "list", "model": MODEL, "data": list(items)} | top


def provider(handler, dim=768, limits=None, env=ENV, model=MODEL):
    return build_provider(load_eval_config("openai", model, env), dim, limits, httpx.MockTransport(handler))


def test_allowlist_is_explicit_and_pinned():
    assert parse_allowlist(f"openai/{MODEL}") == {("openai", MODEL)}
    for bad in ("openai/text-embedding-3-large", "openai/other"):
        with pytest.raises(ConfigError):
            parse_allowlist(bad)
    with pytest.raises(ConfigError):
        load_eval_config("openai", MODEL, {"OPENAI_API_KEY": KEY})  # no allowlist: nothing implicit
    with pytest.raises(ConfigError):
        load_eval_config("openai", MODEL, {ALLOWLIST_VAR: "gemini/m", "OPENAI_API_KEY": KEY})
    with pytest.raises(ConfigError):
        load_eval_config("openai", MODEL, {ALLOWLIST_VAR: f"openai/{MODEL}"})  # key missing


def test_key_isolation():
    other = {ALLOWLIST_VAR: f"openai/{MODEL}", "EMBEDDING_EVAL_OPENAI_API_KEY": "x", "EMBEDDING_EVAL_GEMINI_API_KEY": "y",
             "LLM_API_KEY": "z", "OPENAI_BASE_URL": "http://evil"}
    with pytest.raises(ConfigError):
        load_eval_config("openai", MODEL, other)  # only OPENAI_API_KEY is read
    gem = {ALLOWLIST_VAR: "gemini/m,openai/" + MODEL, "OPENAI_API_KEY": KEY}
    with pytest.raises(ConfigError):
        load_eval_config("gemini", "m", gem)  # the OpenAI key never serves another provider
    assert KEY not in repr(load_eval_config("openai", MODEL, ENV))


def test_model_and_dimension_are_pinned():
    cfg = load_eval_config("openai", MODEL, ENV)
    for dim in (767, 1536, True, "768"):
        with pytest.raises(ConfigError):
            build_provider(cfg, dim, None, httpx.MockTransport(ok))
    from embeddings.config import EvalConfig
    with pytest.raises(ConfigError):
        build_provider(EvalConfig("openai", "text-embedding-3-large", KEY), 768, None, httpx.MockTransport(ok))


def test_request_mapping_and_order():
    seen = []

    def handler(request):
        seen.append(request)
        return ok(request, shuffle=True)  # response out of order: mapped back by index

    res = provider(handler).embed([TEXT, "second"])
    r = seen[0]
    assert r.method == "POST" and str(r.url) == "https://api.openai.com/v1/embeddings" and not r.url.query
    assert r.headers["authorization"] == f"Bearer {KEY}" and KEY not in r.url.raw_path.decode()
    assert json.loads(r.content) == {"model": MODEL, "input": [TEXT, "second"], "dimensions": 768, "encoding_format": "float"}
    assert res.vectors == [vec(0), vec(1)] and res.dimension == 768 and res.item_count == 2 and res.model == MODEL
    assert res.usage == {"prompt_tokens": 7, "total_tokens": 7} and res.request == {"request_id": "req-1", "attempts": 1}


@pytest.mark.parametrize("payload", [
    payload(),
    payload(item(0, vec(0))),  # count short
    payload(item(0, vec(0)), item(0, vec(1))),  # duplicate index
    payload(item(0, vec(0)), item(2, vec(1))),  # gap
    payload(item(1, vec(0)), item(2, vec(1))),  # out of range / does not start at 0
    payload(item(0, vec(0)), item(-1, vec(1))),  # negative
    payload(item(0, vec(0)), {"object": "embedding", "embedding": vec(1)}),  # no index
    payload(item(0, vec(0)), item(False, vec(1))),  # bool index (False == 0, True == 1)
    payload(item(True, vec(0)), item(0, vec(1))),
    payload(item(0.0, vec(0)), item(1.0, vec(1))),  # float index
    payload(item(0, vec(0)), item("1", vec(1))),  # string index
    payload(item(0, vec(0)), item(1, vec(1), object="list")),  # wrong object tag
    payload(item(0, vec(0)), {"index": 1, "embedding": vec(1)}),  # missing object tag
    payload(item(0, vec(0)), "x"),  # item not an object
    payload(item(0, vec(0)), item(1, vec(1)), model="text-embedding-3-large"),  # model substituted
    payload(item(0, vec(0)), item(1, vec(1)), model=None),
    {k: v for k, v in payload(item(0, vec(0)), item(1, vec(1))).items() if k != "model"},  # model missing
    payload(item(0, vec(0)), item(1, "base64==")),  # wrong type
    payload(item(0, vec(0)), item(1, vec(1, 767))),  # wrong dimension
    payload(item(0, vec(0)), item(1, [True] * 768)),  # bool values
    payload(item(0, vec(0)), item(1, [float("nan")] * 768)),
    {"nope": 1},
    [],
])
def test_malformed_responses_are_rejected(payload):
    body = json.dumps(payload)  # emits a NaN literal for the non-finite case, as a real server could
    p = provider(lambda r: httpx.Response(200, content=body, headers={"content-type": "application/json"}))
    with pytest.raises(MalformedResponseError):
        p.embed([TEXT, "second"])


def test_schema_errors_are_redacted_and_not_retried():
    n = {"c": 0}

    def wrong_model(request):
        n["c"] += 1
        return httpx.Response(200, json=payload(item(0, vec(0)), model=f"{KEY}-{TEXT}"))

    with pytest.raises(MalformedResponseError) as e:
        provider(wrong_model).embed([TEXT])
    assert n["c"] == 1 and KEY not in str(e.value) + repr(e.value) and TEXT not in str(e.value)


def test_non_json_response_is_rejected():
    with pytest.raises(MalformedResponseError):
        provider(lambda r: httpx.Response(200, text="<html>")).embed([TEXT])


def test_input_bounds_are_enforced_before_any_call():
    calls = []
    p = provider(lambda r: calls.append(r) or ok(r), limits=EmbeddingLimits(max_batch=2, max_chars=10))
    for bad in ([], ["a", "b", "c"], ["x" * 11], [" "], [1], TEXT):
        with pytest.raises(InputError):
            p.embed(bad)
    assert calls == []


def test_retries_are_bounded_and_transient_only():
    n = {"c": 0}

    def flaky(request):
        n["c"] += 1
        return httpx.Response(429, text=f"slow down {KEY} {TEXT}") if n["c"] == 1 else ok(request)

    assert provider(flaky).embed([TEXT]).request["attempts"] == 2

    n["c"] = 0

    def down(request):
        n["c"] += 1
        return httpx.Response(503, text="down")

    with pytest.raises(ProviderRequestError) as e:
        provider(down).embed([TEXT])
    assert n["c"] == 2 and e.value.status == 503  # one retry, then stop

    n["c"] = 0
    with pytest.raises(ProviderRequestError):
        provider(down, limits=EmbeddingLimits(max_retries=0)).embed([TEXT])
    assert n["c"] == 1

    for status in (400, 401, 403, 404):
        n["c"] = 0

        def fatal(request, status=status):
            n["c"] += 1
            return httpx.Response(status, text=f"bad {KEY}")

        with pytest.raises(ProviderRequestError) as e:
            provider(fatal).embed([TEXT])
        assert n["c"] == 1 and e.value.status == status

    n["c"] = 0

    def boom(request):
        n["c"] += 1
        raise httpx.ConnectError(f"cannot reach {KEY}")

    with pytest.raises(ProviderRequestError):
        provider(boom).embed([TEXT])
    assert n["c"] == 2


def test_typed_errors_are_redacted(caplog):
    caplog.set_level(logging.DEBUG)
    secrets = (KEY, TEXT, "api.openai.com", "0.0")
    cases = (httpx.Response(401, text=f"{KEY} {TEXT}"), httpx.Response(429, text=f"{KEY} {TEXT}"),
             httpx.Response(200, text=f"{KEY} {TEXT} [0.0]"))
    for resp in cases:
        with pytest.raises((ProviderRequestError, MalformedResponseError)) as e:
            provider(lambda r, resp=resp: resp, limits=EmbeddingLimits(max_retries=0)).embed([TEXT])
        shown = str(e.value) + repr(e.value)
        assert not any(s in shown for s in (KEY, TEXT, "[0.0]"))
    assert "credentials" in str(_raises(401)) and "rate limited" in str(_raises(429))
    assert not any(s in caplog.text for s in secrets[:2])


def _raises(status):
    with pytest.raises(ProviderRequestError) as e:
        provider(lambda r: httpx.Response(status), limits=EmbeddingLimits(max_retries=0)).embed([TEXT])
    return e.value


def test_no_fallback_or_second_endpoint():
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(500)

    with pytest.raises(ProviderRequestError):
        provider(handler).embed([TEXT])
    assert set(urls) == {"https://api.openai.com/v1/embeddings"}


def test_adapter_does_not_touch_release_flags_or_app_modules():
    import embeddings.providers.openai as mod
    src = open(mod.__file__, encoding="utf-8").read()
    assert "release" not in src and "environ" not in src and "getenv" not in src
    assert not any(m in src for m in ("import database", "from database", "configuration", "import redis", "import openai"))
