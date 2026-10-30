"""M3-S2 streaming assistant protocol: a deterministic fake provider, bounded and validated, framed as server-sent events.

Provider output is untrusted: every chunk is shape-checked, product cards come from the catalogue (never provider text) and
every action proposal goes through the M3-S1 kernel; the decision (validated or rejected) is streamed next to the proposal.
Nothing is executed: no cart, WhatsApp, order, payment, DB, network or model call happens here.
Events: start, then text|product|proposal in provider order, then exactly one terminal done|error. `seq` counts from 0.
(shortcut: fake provider, one-product in-memory catalogue and a per-stream ledger; swap each in its own reviewed change.)
"""
import hashlib
import json
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping

from actions import kernel as k

PROTOCOL_VERSION = 1
MAX_EVENTS = 40
MAX_TEXT_CHARS = 4000
SERVER_PERMISSIONS = frozenset({"catalogue:read", "cart:propose", "enquiry:initiate"})  # never taken from the client

DEMO_PRODUCT = "11111111-1111-4111-8111-111111111111"
DEMO_VARIANT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def demo_catalogue() -> k.InMemoryCatalogue:
    return k.InMemoryCatalogue({DEMO_PRODUCT: {
        "id": DEMO_PRODUCT, "name": "Pashmina Shawl", "status": "active", "is_active": True, "revision": 7,
        "variants": [{"id": DEMO_VARIANT, "is_active": True, "price": 3500, "currency": "PKR", "stock": 5}],
    }})


def frame(seq: int, event: str, data: dict) -> str:
    """One SSE frame. json.dumps escapes newlines and non-ASCII, so `data` is always a single line."""
    return f"id: {seq}\nevent: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def fake_provider(message: str, idempotency_key: str) -> AsyncIterator[dict]:
    """Scripted, no I/O. 'stale' proposes an out-of-date price, 'boom' raises, 'garbage' emits a malformed chunk."""
    text = message.lower()
    if "boom" in text:
        raise RuntimeError("provider exploded with secret-detail")
    yield {"type": "text", "delta": "Here is a shawl you may like. "}
    if "garbage" in text:
        yield {"type": "banana"}
        return
    yield {"type": "product", "product_id": DEMO_PRODUCT}
    yield {"type": "proposal", "action_type": "show_product", "idempotency_key": _key(idempotency_key, 1),
           "params": {"product_id": DEMO_PRODUCT, "expected_revision": 7}}
    price = 3400 if "stale" in text else 3500
    yield {"type": "proposal", "action_type": "add_to_cart", "idempotency_key": _key(idempotency_key, 2),
           "params": {"product_id": DEMO_PRODUCT, "variant_id": DEMO_VARIANT, "quantity": 1, "expected_revision": 7,
                      "expected_unit_price": price, "currency": "PKR"}}
    yield {"type": "text", "delta": "Say the word and I will help you enquire."}


def _key(base: str, n: int) -> str:
    return "idem_" + hashlib.sha256(f"{base}:{n}".encode()).hexdigest()[:24]


def _bad(code: str) -> dict:
    return {"type": "error", "code": code}


async def stream_events(
    provider: AsyncIterator[Mapping[str, Any]], *, session_id: str, context: dict, idempotency_key: str,
    catalogue: k.CatalogueState, is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[str]:
    """Yield SSE frames. Always closes the provider, including on cancel/disconnect (GeneratorExit/CancelledError)."""
    seq = 0
    ledger = k.IdempotencyLedger()
    ctx = k.ActionContext(session_id=session_id, permissions=SERVER_PERMISSIONS)
    chars = 0

    def out(event: str, data: dict) -> str:
        nonlocal seq
        seq += 1
        return frame(seq - 1, event, data)

    try:
        yield out("start", {"protocol": PROTOCOL_VERSION, "session_id": session_id, "context": context,
                            "idempotency_key": idempotency_key})
        terminal: tuple[str, dict] = ("done", {"events": 0})
        count = 0
        try:
            async for chunk in provider:
                if is_disconnected is not None and await is_disconnected():
                    return  # client went away: stop quietly, no terminal frame can be delivered
                count += 1
                if count > MAX_EVENTS:
                    terminal = ("error", {"code": "provider_overrun"})
                    break
                kind = chunk.get("type") if isinstance(chunk, Mapping) else None
                if kind == "text":
                    delta = chunk.get("delta")
                    chars += len(delta) if isinstance(delta, str) else 0
                    if not isinstance(delta, str) or not delta or chars > MAX_TEXT_CHARS:
                        terminal = ("error", {"code": "provider_malformed"})
                        break
                    yield out("text", {"delta": delta})
                elif kind == "product":
                    pid = chunk.get("product_id")
                    p = catalogue.get(pid) if isinstance(pid, str) else None
                    if not p or p.get("status") != "active" or p.get("is_active") is not True:
                        terminal = ("error", {"code": "provider_malformed"})
                        break
                    v = next((v for v in p.get("variants", ()) if v.get("is_active") is True), {})
                    yield out("product", {"product_id": pid, "name": str(p.get("name", ""))[:200], "revision": p.get("revision"),
                                          "price": v.get("price"), "currency": v.get("currency")})
                elif kind == "proposal":
                    proposal = k.ActionProposal(chunk.get("action_type"), chunk.get("idempotency_key"), chunk.get("params"), ctx)
                    decision = k.validate(proposal, catalogue, ledger)
                    # Only allowlisted names are echoed; everything else about a rejected proposal stays out of the stream.
                    yield out("proposal", {"action_type": decision.action_type, "idempotency_key": decision.idempotency_key,
                                           "session_id": session_id, "decision": decision.audit()})
                else:
                    terminal = ("error", {"code": "provider_malformed"})
                    break
        except Exception:  # provider failure: fixed code only, never the exception text
            terminal = ("error", {"code": "provider_error"})
        if terminal[0] == "done":
            terminal = ("done", {"events": seq})
        yield out(*terminal)
    finally:
        aclose = getattr(provider, "aclose", None)
        if aclose is not None:
            await aclose()
