"""M3-S3: confirmed-only execution, kernel revalidation, replay/conflict binding, inert WhatsApp handoff, flag. Container-free."""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actions import execution as x
from actions import kernel as k
from routes import action_routes as r

AID, SID, NOW = "act_0123456789abcdef0123", "sess-1", 1_000.0
PID, VID = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
LINE = {"product_id": PID, "variant_id": VID, "quantity": 2}


def proposal(name="add_to_cart", params=None, aid=AID, sid=SID, confirm=True, **conf):
    params = params or (LINE if name == "add_to_cart" else {"items": [LINE]})
    fp = k._fingerprint(name, sid, k._normalise(name, params))
    c = Confirmation(aid, sid, fp, **conf) if confirm else None
    return k.ActionProposal(aid, name, sid, params, {"hard": {}}, c)


def Confirmation(aid, sid, fp, **o):
    return k.Confirmation(**{"action_id": aid, "session_id": sid, "fingerprint": fp, "confirmed_at": NOW - 1,
                             "expires_at": NOW + 60, "explicit": True, **o})


async def ok(lines):
    return True


async def gone(lines):
    return False


def run(p, store=None, check=ok, now=NOW):
    return asyncio.run(x.execute(p, store=store or x.MemoryStore(), check_lines=check, now=now))


def test_add_to_cart_returns_normalised_client_lines():
    out = run(proposal())
    assert (out.status, out.replayed) == ("executed", False)
    assert out.result["intent"] == {"type": "add_to_cart", "action_id": AID, "items": [LINE], "applied_by": "client_cart"}
    assert out.result["acknowledged"] is True


def test_whatsapp_handoff_is_inert():
    i = run(proposal("start_whatsapp_order")).result["intent"]
    assert i["sent"] is False and i["order_confirmed"] is False and i["next"] == "client_whatsapp_handoff"


@pytest.mark.parametrize("p,reason", [
    (proposal(confirm=False), "confirmation_required"),
    (proposal(explicit=False), "confirmation_invalid"),
    (proposal(expires_at=NOW - 1), "confirmation_invalid"),  # zero TTL
    (proposal(confirmed_at=NOW - 400, expires_at=NOW - 100), "confirmation_expired"),
    (proposal(sid="other", confirm=True), "ok"),  # a different session is just a different, valid key
])
def test_confirmation_is_required_explicit_and_unexpired(p, reason):
    out = run(p)
    assert out.reason == reason and (out.status == "executed") == (reason == "ok")


def test_confirmation_for_other_params_is_rejected():
    p = proposal()
    forged = k.ActionProposal(AID, "add_to_cart", SID, {**LINE, "quantity": 9}, p.constraints, p.confirmation)
    assert run(forged).reason == "confirmation_mismatch"


@pytest.mark.parametrize("name", ["show_products", "open_product", "apply_filters"])
def test_non_executable_actions_are_rejected(name):
    params = {"product_ids": [PID]} if name == "show_products" else {"product_id": PID} if name == "open_product" else {"filters": {"color": "red"}}
    assert run(k.ActionProposal(AID, name, SID, params, {"hard": {}})).reason == "unsupported_action"


def test_duplicate_confirmed_request_replays_and_conflict_is_rejected():
    store = x.MemoryStore()
    first = run(proposal(), store)
    again = run(proposal(), store)
    assert again.replayed and again.result == first.result
    other = proposal(params={**LINE, "quantity": 3})  # same session + action id, different fingerprint
    assert run(other, store).reason == "idempotency_conflict"
    assert run(proposal(aid="act_other0123456789abcdef"), store).replayed is False


def test_unavailable_item_is_rejected_and_not_stored():
    store = x.MemoryStore()
    assert run(proposal(), store, check=gone).reason == "unavailable_item"
    assert run(proposal(), store).replayed is False


def test_concurrent_duplicates_execute_once():
    async def both():
        s = x.MemoryStore()
        return await asyncio.gather(*(x.execute(proposal(), store=s, check_lines=ok, now=NOW) for _ in range(5)))
    assert sorted(o.replayed for o in asyncio.run(both())) == [False, True, True, True, True]


def test_store_is_bounded():
    s = x.MemoryStore(max_entries=2)
    for i in range(5):
        asyncio.run(s.claim(SID, f"a{i}", "f", "add_to_cart", {}))
    assert len(s._rows) == 2


def test_route_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ASSISTANT_ACTIONS_ENABLED", raising=False)
    app = FastAPI()
    app.include_router(r.router)
    app.dependency_overrides[r.get_pg_session] = lambda: None
    res = TestClient(app).post("/v1/assistant/actions/execute", json={"action_id": AID, "name": "add_to_cart", "session_id": SID, "params": LINE})
    assert res.status_code == 503 and res.json()["error"] == "actions_disabled"
