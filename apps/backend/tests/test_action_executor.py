"""M3-S3 execution adapters: only explicit, user-confirmed, freshly revalidated, idempotent execution. Fakes only."""
import asyncio
import json

import pytest

from actions import executor as x
from actions import kernel as k
from tests.test_action_kernel import ALL, KEY, P1, V1, cart, catalogue, ctx, item


def enquiry(key=KEY, **over):
    return k.ActionProposal("start_whatsapp_enquiry", key, {"items": [item(**over)]}, ctx())


class Spy:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    async def __call__(self, action, params):
        self.calls.append((action, params))
        if self.fail:
            raise self.fail
        return {"reference": f"ES-{len(self.calls)}"}


def _load(cat):
    async def load():
        return cat
    return load


def run(proposal, cat=None, spy=None, ledger=None, audit=None, confirmed=True):
    spy = spy if spy is not None else Spy()
    ledger = ledger if ledger is not None else x.ExecutionLedger()
    sink = audit if audit is not None else []
    out = asyncio.run(x.execute(proposal, confirmed=confirmed, load_catalogue=_load(cat or catalogue()), perform=spy, ledger=ledger, audit=sink.append))
    return out, spy, sink


def test_executes_once_after_confirmation_and_audits_safely():
    out, spy, sink = run(enquiry())
    assert (out.outcome, out.reason, out.replayed, out.result) == ("executed", "ok", False, {"reference": "ES-1"})
    assert len(spy.calls) == 1 and spy.calls[0][0] == "start_whatsapp_enquiry"
    rec = sink[0]
    assert rec["executed"] is True and rec["outcome"] == "executed" and rec["action_type"] == "start_whatsapp_enquiry"
    blob = json.dumps(rec)
    assert "sess-secret-123" not in blob and "user-pii-42" not in blob and '"expected_unit_price"' not in blob


@pytest.mark.parametrize("confirmed", [False, None, "true", 1])
def test_unconfirmed_never_executes(confirmed):
    out, spy, sink = run(cart(), confirmed=confirmed)
    assert (out.outcome, out.reason) == ("rejected", "not_confirmed") and spy.calls == []
    assert sink[0]["executed"] is False


@pytest.mark.parametrize("over, reason", [
    ({"expected_unit_price": 3400}, "stale_price"), ({"expected_revision": 6}, "stale_revision"), ({"quantity": 6}, "insufficient_stock"),
])
def test_current_state_is_rechecked_and_failures_do_not_execute(over, reason):
    out, spy, sink = run(cart(**over))
    assert (out.outcome, out.reason) == ("rejected", reason) and spy.calls == [] and sink[0]["executed"] is False


def test_state_change_between_proposal_and_confirmation_rejects():
    proposal = enquiry()
    assert k.validate(proposal, catalogue(), k.IdempotencyLedger()).outcome == "validated"
    out, spy, _ = run(proposal, cat=catalogue(variants=[{"id": V1, "is_active": True, "price": 3500, "currency": "PKR", "stock": 0}]))
    assert out.reason == "out_of_stock" and spy.calls == []


def test_show_product_and_missing_permission_are_not_executable():
    show = k.ActionProposal("show_product", KEY, {"product_id": P1, "expected_revision": 7}, ctx())
    assert run(show)[0].reason == "unsupported_action"
    assert run(cart(context=ctx(permissions=frozenset())))[0].reason == "permission_denied"


def test_replay_returns_stored_result_without_second_execution():
    ledger, spy = x.ExecutionLedger(), Spy()
    first, _, _ = run(enquiry(), spy=spy, ledger=ledger)
    again, _, sink = run(enquiry(), spy=spy, ledger=ledger)
    assert again.outcome == "executed" and again.replayed is True and again.result == first.result
    assert len(spy.calls) == 1 and sink[0]["replayed"] is True


def test_same_key_with_different_params_conflicts():
    ledger, spy = x.ExecutionLedger(), Spy()
    run(enquiry(), spy=spy, ledger=ledger)
    out, _, _ = run(enquiry(quantity=3), spy=spy, ledger=ledger)
    assert out.reason == "idempotency_conflict" and len(spy.calls) == 1


def test_concurrent_duplicates_execute_once():
    spy, ledger = Spy(), x.ExecutionLedger()

    async def go():
        return await asyncio.gather(*[x.execute(enquiry(), confirmed=True, load_catalogue=_load(catalogue()), perform=spy, ledger=ledger, audit=lambda r: None) for _ in range(5)])

    outs = asyncio.run(go())
    assert len(spy.calls) == 1 and all(o.outcome == "executed" for o in outs) and sum(o.replayed for o in outs) == 4


def test_failed_execution_is_visible_and_retryable_with_same_key():
    ledger = x.ExecutionLedger()
    out, _, sink = run(enquiry(), spy=Spy(fail=RuntimeError("db password=hunter2")), ledger=ledger)
    assert (out.outcome, out.reason) == ("rejected", "execution_failed") and "hunter2" not in json.dumps(sink)
    retry, spy, _ = run(enquiry(), ledger=ledger)
    assert retry.outcome == "executed" and len(spy.calls) == 1


def test_ledger_is_bounded():
    ledger = x.ExecutionLedger(max_entries=2)
    for n in range(4):
        ledger.put("s", f"idem_{n:016d}", "fp", {})
    assert len(ledger._done) == 2 and ledger.get("s", "idem_0000000000000000") is None
