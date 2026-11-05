"""Feature-flagged assistant stream in the AI SDK UI message stream protocol (v1, SSE).

A provider proposes tool calls; every proposal goes through the action kernel and is reported, never executed.
The loop is bounded by MAX_STEPS and a per-step/total timeout. No network, keys or side effects.
"""
import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator, Awaitable, Callable

from actions.kernel import ActionProposal, Confirmation, InMemoryLedger, validate
from assistant.prompt import PROMPT_VERSION, SYSTEM_PROMPT
from assistant.tools import TOOLS

STREAM_HEADER = {"x-vercel-ai-ui-message-stream": "v1"}
MAX_STEPS = 4
MAX_CALLS_PER_STEP = 5
STEP_TIMEOUT = 2.0  # seconds per provider call
TOTAL_TIMEOUT = 8.0

Provider = Callable[[int, str, list], Awaitable[Any]]
LEDGER = InMemoryLedger()  # shortcut: process-local; durable replay is a later batch


class BadProviderOutput(Exception):
    pass


def sse(chunk: dict | str) -> str:
    return f"data: {chunk if isinstance(chunk, str) else json.dumps(chunk, separators=(',', ':'))}\n\n"


def _check_step(out: Any) -> tuple[str, list[dict]]:
    """Provider output must be {"text"?: str, "tool_calls"?: [{name, input, action_id, constraints?, confirmation?}]}."""
    if not isinstance(out, dict) or set(out) - {"text", "tool_calls"}:
        raise BadProviderOutput
    text, calls = out.get("text", ""), out.get("tool_calls", [])
    if not isinstance(text, str) or len(text) > 2000 or not isinstance(calls, list) or len(calls) > MAX_CALLS_PER_STEP:
        raise BadProviderOutput
    for c in calls:
        if not isinstance(c, dict) or not set(c) <= {"name", "input", "action_id", "constraints", "confirmation"}:
            raise BadProviderOutput
        if not isinstance(c.get("name"), str) or not isinstance(c.get("input"), dict):
            raise BadProviderOutput
    return text, calls


def _confirmation(raw: Any):
    if raw is None:
        return None
    try:
        return Confirmation(**raw)
    except Exception:
        return raw  # kernel rejects a non-Confirmation as confirmation_invalid


def propose(call: dict, session_id: str, ledger: InMemoryLedger, now: float) -> dict:
    """Registry gate, then the kernel. Returns the tool output; `executed` is always False."""
    name = call["name"]
    if name not in TOOLS:
        return {"outcome": "rejected", "reason": "unknown_tool", "action": "unknown", "executed": False}
    constraints = call.get("constraints") or {"hard": {}}
    d = validate(ActionProposal(call.get("action_id"), name, session_id, call["input"], constraints,
                                _confirmation(call.get("confirmation"))), ledger, now)
    return {"outcome": d.outcome, "reason": d.reason, "action": d.action, "action_id": d.action_id,
            "fingerprint": d.fingerprint, "replayed": d.replayed, "executed": False,
            "requires_confirmation": d.outcome == "needs_confirmation",
            "relaxation_acknowledged": bool(constraints.get("relaxation_acknowledged")) if isinstance(constraints, dict) else False,
            "prompt_version": PROMPT_VERSION}


async def _steps(provider: Provider, message: str, session_id: str, ledger: InMemoryLedger,
                 clock: Callable[[], float]) -> AsyncIterator[dict]:
    results: list = []
    for step in range(MAX_STEPS):
        text, calls = _check_step(await asyncio.wait_for(provider(step, message, results), STEP_TIMEOUT))
        outs = [(c, propose(c, session_id, ledger, clock())) for c in calls]
        results.extend(o for _, o in outs)
        yield {"step": step, "text": text, "outs": outs}
        if not calls:
            return
    # step budget exhausted while the provider still wanted tools: stop, report in the caller


async def run(provider: Provider, message: str, session_id: str, ledger: InMemoryLedger | None = None,
              clock: Callable[[], float] = time.time) -> AsyncIterator[str]:
    ledger = LEDGER if ledger is None else ledger
    yield sse({"type": "start", "messageId": f"msg_{uuid.uuid4().hex}"})
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT):
            last_had_calls = False
            async for s in _steps(provider, message, session_id, ledger, clock):
                yield sse({"type": "start-step"})
                if s["text"]:
                    tid = f"txt_{s['step']}"
                    yield sse({"type": "text-start", "id": tid})
                    yield sse({"type": "text-delta", "id": tid, "delta": s["text"]})
                    yield sse({"type": "text-end", "id": tid})
                for i, (call, out) in enumerate(s["outs"]):
                    cid = f"call_{s['step']}_{i}"
                    yield sse({"type": "tool-input-available", "toolCallId": cid, "toolName": str(call["name"])[:64],
                               "input": call["input"]})
                    yield sse({"type": "tool-output-available", "toolCallId": cid, "output": out})
                yield sse({"type": "finish-step"})
                last_had_calls = bool(s["outs"])
            if last_had_calls:
                raise BadProviderOutput  # never settled within MAX_STEPS
        yield sse({"type": "finish"})
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        yield sse({"type": "error", "errorText": "assistant_timeout"})
    except BadProviderOutput:
        yield sse({"type": "error", "errorText": "invalid_provider_output"})
    except Exception:  # never echo internals
        yield sse({"type": "error", "errorText": "assistant_failed"})
    yield sse("[DONE]")


_PID = "11111111-1111-4111-8111-111111111111"
_VID = "22222222-2222-4222-8222-222222222222"


async def fake_provider(step: int, message: str, results: list) -> dict:
    """Deterministic scripted provider keyed off the message; step 1 summarises, never loops."""
    m = message.lower()
    if step > 0:
        return {"text": "Done. Nothing was executed; confirm to proceed."}
    aid = "act_" + uuid.uuid5(uuid.NAMESPACE_URL, m).hex
    if "cart" in m:
        return {"text": "I can add that once you confirm.", "tool_calls": [
            {"name": "add_to_cart", "action_id": aid, "input": {"product_id": _PID, "variant_id": _VID, "quantity": 1}}]}
    if "open" in m:
        return {"tool_calls": [{"name": "open_product", "action_id": aid, "input": {"product_id": _PID}}]}
    return {"text": "Here is a shawl.", "tool_calls": [
        {"name": "show_products", "action_id": aid, "input": {"product_ids": [_PID]}}]}
