"""M3-S2 streaming assistant: framing, ordering, cancel/disconnect, malformed provider output, kernel validation, no external calls."""
import asyncio
import functools
import json
import re
import socket

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from assistant import stream as s
from routes import assistant_routes as r

KEY = "idem_0123456789abcdef"


def sync(fn):
    @functools.wraps(fn)
    def run(*a, **kw):
        return asyncio.run(fn(*a, **kw))
    return run


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def no_net(*a, **k_):
        raise AssertionError("network used")
    monkeypatch.setattr(socket, "create_connection", no_net)
    monkeypatch.setattr(socket, "getaddrinfo", no_net)


def parse(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        assert [l.split(": ", 1)[0] for l in lines] == ["id", "event", "data"]
        out.append((int(lines[0][4:]), lines[1][7:], json.loads(lines[2][6:])))
    return out


async def collect(provider, **over):
    kw = dict(session_id="sess-1", context={"page": "p"}, idempotency_key=KEY, catalogue=s.demo_catalogue())
    kw.update(over)
    return [f async for f in s.stream_events(provider, **kw)]


def client(provider=None):
    app = FastAPI()
    app.include_router(r.router)
    if provider:
        app.dependency_overrides[r.get_provider] = lambda: provider
    return TestClient(app)


def body(**over):
    return {"session_id": "sess-1", "idempotency_key": KEY, "message": "show me a shawl", "context": {"page": "home"}, **over}


def test_http_stream_framing_order_and_metadata():
    resp = client().post("/v1/assistant/stream", json=body())
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-store"
    ev = parse(resp.text)
    assert [e[0] for e in ev] == list(range(len(ev)))
    assert [e[1] for e in ev] == ["start", "text", "product", "proposal", "proposal", "text", "done"]
    assert ev[0][2] == {"protocol": 1, "session_id": "sess-1", "context": {"page": "home"}, "idempotency_key": KEY}
    assert ev[-1][2] == {"events": 6}
    assert all(e[2]["session_id"] == "sess-1" for e in ev if e[1] == "proposal")


def test_product_comes_from_catalogue_and_proposals_are_kernel_validated():
    ev = parse(client().post("/v1/assistant/stream", json=body()).text)
    product = next(e[2] for e in ev if e[1] == "product")
    assert product == {"product_id": s.DEMO_PRODUCT, "name": "Pashmina Shawl", "revision": 7, "price": 3500, "currency": "PKR", "in_stock": True}
    props = [e[2] for e in ev if e[1] == "proposal"]
    assert [p["decision"]["outcome"] for p in props] == ["validated", "validated"]
    assert all(p["decision"]["executed"] is False for p in props)
    assert props[1]["idempotency_key"] == props[1]["decision"]["idempotency_key"] != KEY


def test_stale_proposal_is_streamed_as_rejected():
    ev = parse(client().post("/v1/assistant/stream", json=body(message="stale please")).text)
    d = [e[2]["decision"] for e in ev if e[1] == "proposal"][1]
    assert (d["outcome"], d["reason"], d["executed"]) == ("rejected", "stale_price", False)
    assert ev[-1][1] == "done"


@pytest.mark.parametrize("bad", [
    {"session_id": "has space"}, {"idempotency_key": "nope"}, {"message": ""}, {"message": "x" * 501},
    {"context": {"k": "v" * 201}}, {"context": {f"k{i}": 1 for i in range(11)}},
])
def test_bad_request_is_422_before_any_stream(bad):
    resp = client().post("/v1/assistant/stream", json=body(**bad))
    assert resp.status_code == 422 and "event-stream" not in resp.headers["content-type"]


def test_client_cannot_grant_permissions():
    resp = client().post("/v1/assistant/stream", json=body(permissions=["admin"], context={"permissions": "x"}))
    assert resp.status_code == 200  # extra field ignored; context is only echoed
    assert s.SERVER_PERMISSIONS == frozenset({"catalogue:read", "cart:propose", "enquiry:initiate"})


def test_provider_exception_becomes_fixed_error_without_detail():
    resp = client().post("/v1/assistant/stream", json=body(message="boom"))
    ev = parse(resp.text)
    assert [e[1] for e in ev] == ["start", "error"]
    assert ev[-1][2] == {"code": "provider_error"}
    assert "secret-detail" not in resp.text


def test_malformed_chunk_ends_with_error_after_earlier_events():
    ev = parse(client().post("/v1/assistant/stream", json=body(message="garbage")).text)
    assert [e[1] for e in ev] == ["start", "text", "error"]
    assert ev[-1][2] == {"code": "provider_malformed"}


@pytest.mark.parametrize("chunk", [
    "str", None, {"type": "text"}, {"type": "text", "delta": ""}, {"type": "text", "delta": 5},
    {"type": "product", "product_id": "99999999-9999-4999-8999-999999999999"}, {"type": "product"},
])
@sync
async def test_malformed_provider_chunks(chunk):
    async def prov():
        yield chunk
    frames = await collect(prov())
    assert [e[1] for e in parse("".join(frames))] == ["start", "error"]


@sync
async def test_unknown_and_malformed_proposals_are_rejected_not_raised():
    async def prov():
        yield {"type": "proposal", "action_type": "<script>alert(1)</script>", "idempotency_key": 5, "params": []}
        yield {"type": "proposal", "action_type": "place_order", "params": {}}
    ev = parse("".join(await collect(prov())))
    decisions = [e[2] for e in ev if e[1] == "proposal"]
    assert [d["decision"]["outcome"] for d in decisions] == ["rejected", "rejected"]
    assert all(d["action_type"] == "unknown" for d in decisions)
    assert "script" not in "".join(json.dumps(d) for d in decisions)
    assert ev[-1][1] == "done"


@sync
async def test_idempotency_replay_and_conflict_within_stream():
    good = {"type": "proposal", "action_type": "show_product", "idempotency_key": KEY,
            "params": {"product_id": s.DEMO_PRODUCT, "expected_revision": 7}}
    other = {**good, "params": {"product_id": s.DEMO_PRODUCT, "expected_revision": 8}}

    async def prov():
        yield good
        yield good
        yield other
    d = [e[2]["decision"] for e in parse("".join(await collect(prov()))) if e[1] == "proposal"]
    assert [(x["outcome"], x["replayed"], x["reason"]) for x in d] == [
        ("validated", False, "ok"), ("validated", True, "ok"), ("rejected", False, "idempotency_conflict")]


@sync
async def test_event_and_text_bounds():
    async def many():
        for _ in range(s.MAX_EVENTS + 1):
            yield {"type": "text", "delta": "a"}

    async def big():
        yield {"type": "text", "delta": "a" * (s.MAX_TEXT_CHARS + 1)}
    assert parse("".join(await collect(many())))[-1][2] == {"code": "provider_overrun"}
    assert parse("".join(await collect(big())))[-1][2] == {"code": "provider_malformed"}


@sync
async def test_cancel_closes_provider_and_emits_nothing_more():
    closed = []

    async def prov():
        try:
            for i in range(100):
                yield {"type": "text", "delta": f"{i}"}
        finally:
            closed.append(True)
    gen = s.stream_events(prov(), session_id="sess-1", context={}, idempotency_key=KEY, catalogue=s.demo_catalogue())
    assert "event: start" in await gen.__anext__()
    assert "event: text" in await gen.__anext__()
    await gen.aclose()  # what Starlette does when the client cancels
    assert closed == [True]
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


@sync
async def test_disconnect_stops_stream_without_terminal_frame():
    closed = []
    calls = {"n": 0}

    async def prov():
        try:
            for i in range(10):
                yield {"type": "text", "delta": "x"}
        finally:
            closed.append(True)

    async def gone():
        calls["n"] += 1
        return calls["n"] > 2
    ev = parse("".join(await collect(prov(), is_disconnected=gone)))
    assert [e[1] for e in ev] == ["start", "text", "text"] and closed == [True]


def test_frames_are_single_line_even_with_newlines_and_unicode():
    f = s.frame(3, "text", {"delta": "a\nb c\r\n\nd"})
    assert f.count("\n") == 4 and f.endswith("\n\n")
    assert json.loads(f.split("data: ")[1])["delta"] == "a\nb c\r\n\nd"


def test_modules_import_nothing_that_can_reach_out_or_mutate():
    allowed = {"hashlib", "json", "typing", "actions", "re", "fastapi", "pydantic"}
    for mod in (s, r):
        roots = set(re.findall(r"^(?:from|import) ([\w]+)", open(mod.__file__).read(), re.M))
        assert roots - allowed - {"assistant"} == set(), (mod.__name__, roots)


def test_only_validated_executable_proposals_carry_params_for_the_confirmation_step():
    props = [e[2] for e in parse(client().post("/v1/assistant/stream", json=body()).text) if e[1] == "proposal"]
    assert "params" not in props[0]  # show_product is not executable
    assert props[1]["params"]["quantity"] == 1 and props[1]["params"]["expected_unit_price"] == 3500
    stale = [e[2] for e in parse(client().post("/v1/assistant/stream", json=body(message="stale")).text) if e[1] == "proposal"]
    assert "params" not in stale[1]  # rejected: nothing to confirm
