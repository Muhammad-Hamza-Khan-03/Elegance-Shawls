"""M3-S2: UI message stream framing/order/terminal event, malformed output, flag, bounded loop, kernel gate, replay, offline."""
import asyncio
import json
import socket

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actions.kernel import InMemoryLedger
from assistant import stream as s
from assistant.tools import TOOLS
from routes import assistant_routes as r

PID, VID = s._PID, s._VID
AID = "act_0123456789abcdef0123"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def no_net(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(socket, "create_connection", no_net)
    monkeypatch.setattr(socket, "getaddrinfo", no_net)
    monkeypatch.setenv("ASSISTANT_STREAM_ENABLED", "true")
    monkeypatch.setattr(s, "LEDGER", InMemoryLedger())


def client(provider=None):
    app = FastAPI()
    app.include_router(r.router)
    if provider:
        app.dependency_overrides[r.get_provider] = lambda: provider
    return TestClient(app)


def frames(text):
    out = [b[len("data: "):] for b in text.strip().split("\n\n")]
    return [f if f == "[DONE]" else json.loads(f) for f in out]


def post(provider=None, message="show me a shawl", session="sess-1"):
    resp = client(provider).post("/v1/assistant/stream", json={"session_id": session, "message": message})
    return resp, frames(resp.text)


def types(fr):
    return [f if isinstance(f, str) else f["type"] for f in fr]


def provider_of(*steps):
    async def p(step, message, results):
        return steps[min(step, len(steps) - 1)]
    return p


def call(name="show_products", inp=None, **kw):
    return {"name": name, "action_id": AID, "input": inp or {"product_ids": [PID]}, **kw}


def test_framing_order_and_terminal():
    resp, fr = post()
    assert resp.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert types(fr) == ["start", "start-step", "text-start", "text-delta", "text-end", "tool-input-available",
                         "tool-output-available", "finish-step", "start-step", "text-start", "text-delta", "text-end",
                         "finish-step", "finish", "[DONE]"]
    assert fr[0]["messageId"].startswith("msg_")


def test_action_id_and_acknowledgement_fields_in_output():
    _, fr = post(message="add to cart")
    out = next(f for f in fr if f != "[DONE]" and f["type"] == "tool-output-available")["output"]
    assert out["action_id"].startswith("act_") and out["outcome"] == "needs_confirmation"
    assert out["requires_confirmation"] is True and out["relaxation_acknowledged"] is False and out["executed"] is False
    assert out["fingerprint"] and out["prompt_version"] == s.PROMPT_VERSION


def test_registry_is_exactly_the_five_actions():
    assert set(TOOLS) == {"show_products", "open_product", "apply_filters", "add_to_cart", "start_whatsapp_order"}


def test_disabled_flag_is_graceful(monkeypatch):
    monkeypatch.setenv("ASSISTANT_STREAM_ENABLED", "false")
    resp, _ = client().post("/v1/assistant/stream", json={"session_id": "s", "message": "hi"}), None
    assert resp.status_code == 503 and resp.json() == {"enabled": False, "error": "assistant_disabled"}
    assert "x-vercel-ai-ui-message-stream" not in resp.headers


@pytest.mark.parametrize("bad", [None, "text", [], {"text": 5}, {"tool_calls": "x"}, {"extra": 1},
                                 {"tool_calls": [{"name": 1, "input": {}}]}, {"tool_calls": [{"name": "open_product"}]},
                                 {"tool_calls": [{"name": "open_product", "input": {}, "evil": 1}]},
                                 {"tool_calls": [{"name": "show_products", "input": {}}] * 6}])
def test_malformed_provider_output_ends_with_error_then_done(bad):
    _, fr = post(provider_of(bad))
    assert types(fr) == ["start", "error", "[DONE]"] and fr[1]["errorText"] == "invalid_provider_output"


def test_provider_exception_does_not_leak():
    async def boom(*a):
        raise RuntimeError("secret-key-123")
    resp, fr = post(boom)
    assert fr[-2]["errorText"] == "assistant_failed" and "secret" not in resp.text


def test_loop_is_bounded_by_max_steps():
    calls = []

    async def forever(step, message, results):
        calls.append(step)
        return {"tool_calls": [call()]}
    _, fr = post(forever)
    assert len(calls) == s.MAX_STEPS
    assert fr[-2]["errorText"] == "invalid_provider_output" and fr[-1] == "[DONE]"


def test_timeout_is_bounded(monkeypatch):
    monkeypatch.setattr(s, "STEP_TIMEOUT", 0.05)

    async def slow(*a):
        await asyncio.sleep(5)
    _, fr = post(slow)
    assert fr[-2]["errorText"] == "assistant_timeout" and fr[-1] == "[DONE]"


def outputs(fr):
    return [f["output"] for f in fr if f != "[DONE]" and f["type"] == "tool-output-available"]


def test_kernel_rejects_invalid_and_unknown():
    _, fr = post(provider_of({"tool_calls": [call(inp={"product_ids": ["nope"]}), call("delete_everything"),
                                             call("open_product", {"product_id": PID, "x": 1})]}, {}))
    outs = outputs(fr)
    assert [(o["outcome"], o["reason"]) for o in outs] == [
        ("rejected", "invalid_params"), ("rejected", "unknown_tool"), ("rejected", "invalid_params")]
    assert all(o["executed"] is False for o in outs)


def test_silent_relaxation_rejected_then_acknowledged():
    hard = {"hard": {"colour": "red"}, "relaxed": ["colour"]}
    _, fr = post(provider_of({"tool_calls": [call("apply_filters", {"filters": {"colour": "blue"}}, constraints=hard)]}, {}))
    assert outputs(fr)[0]["reason"] == "silent_relaxation"
    ok = {**hard, "relaxation_acknowledged": True}
    _, fr = post(provider_of({"tool_calls": [call("apply_filters", {"filters": {"colour": "blue"}}, constraints=ok)]}, {}),
                 session="sess-2")
    assert outputs(fr)[0]["outcome"] == "validated" and outputs(fr)[0]["relaxation_acknowledged"] is True


def test_replay_and_conflict_across_requests():
    _, a = post(provider_of({"tool_calls": [call()]}, {}))
    _, b = post(provider_of({"tool_calls": [call()]}, {}))
    assert (outputs(a)[0]["outcome"], outputs(a)[0]["replayed"]) == ("validated", False)
    assert (outputs(b)[0]["outcome"], outputs(b)[0]["replayed"]) == ("validated", True)
    _, c = post(provider_of({"tool_calls": [call(inp={"product_ids": [VID]})]}, {}))
    assert outputs(c)[0]["reason"] == "idempotency_conflict"
    _, d = post(provider_of({"tool_calls": [call(inp={"product_ids": [VID]})]}, {}), session="sess-other")
    assert outputs(d)[0]["outcome"] == "validated"  # ledger is per session


def test_confirmation_flow_validates_but_never_executes():
    line = {"product_id": PID, "variant_id": VID, "quantity": 1}
    _, first = post(provider_of({"tool_calls": [call("add_to_cart", line)]}, {}))
    fp = outputs(first)[0]["fingerprint"]
    import time
    now = time.time()
    conf = {"action_id": AID, "session_id": "sess-1", "fingerprint": fp, "confirmed_at": now - 1,
            "expires_at": now + 60, "explicit": True}
    _, second = post(provider_of({"tool_calls": [call("add_to_cart", line, confirmation=conf)]}, {}))
    o = outputs(second)[0]
    assert o["outcome"] == "validated" and o["executed"] is False


def test_invalid_request_body_rejected():
    assert client().post("/v1/assistant/stream", json={"session_id": "s", "message": ""}).status_code == 422
    assert client().post("/v1/assistant/stream", json={"session_id": "s", "message": "x", "k": 1}).status_code == 422
