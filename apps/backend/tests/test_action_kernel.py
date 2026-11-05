"""M3-S1 action kernel: allowlist, malformed input, replay/conflict, expiry, session binding, no silent relaxation."""
import socket

import pytest

from actions import kernel as k

P1 = "11111111-1111-4111-8111-111111111111"
V1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
AID = "act_0123456789abcdef"
SID = "sess-1"
NOW = 1000.0


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def no_net(*a, **kw):
        raise AssertionError("network used")
    monkeypatch.setattr(socket, "socket", no_net)
    monkeypatch.setattr(socket, "create_connection", no_net)


LINE = {"product_id": P1, "variant_id": V1, "quantity": 2}
PARAMS = {
    "show_products": {"product_ids": [P1], "filters": {"colour": "red"}},
    "open_product": {"product_id": P1, "variant_id": V1},
    "apply_filters": {"filters": {"colour": "red"}},
    "add_to_cart": LINE,
    "start_whatsapp_order": {"items": [LINE]},
}
HARD = {"hard": {"colour": "red"}}


def prop(name="open_product", params=None, **over):
    base = dict(action_id=AID, name=name, session_id=SID, params=PARAMS[name] if params is None else params,
                constraints=HARD if name in ("show_products", "apply_filters") else {"hard": {}})
    base.update(over)
    return k.ActionProposal(**base)


def conf(p, **over):
    fp = k.validate(p, k.InMemoryLedger(), NOW).fingerprint
    base = dict(action_id=AID, session_id=SID, fingerprint=fp, confirmed_at=NOW - 10, expires_at=NOW + 60, explicit=True)
    base.update(over)
    return k.Confirmation(**base)


def run(p, ledger=None, now=NOW):
    return k.validate(p, ledger if ledger is not None else k.InMemoryLedger(), now)


def test_allowlist_is_exact():
    assert k.ACTIONS == set(PARAMS)
    assert k.CONFIRMATION_REQUIRED == {"add_to_cart", "start_whatsapp_order"}


@pytest.mark.parametrize("name", ["show_products", "open_product", "apply_filters"])
def test_read_only_actions_validate_without_confirmation(name):
    d = run(prop(name))
    assert (d.outcome, d.reason, d.executed) == ("validated", "ok", False)


@pytest.mark.parametrize("name", ["add_to_cart", "start_whatsapp_order"])
def test_mutating_actions_need_then_accept_confirmation(name):
    p = prop(name)
    assert run(p).outcome == "needs_confirmation"
    d = run(prop(name, confirmation=conf(p)))
    assert (d.outcome, d.executed) == ("validated", False)


@pytest.mark.parametrize("name", ["checkout", "show_product", "place_order", "ADD_TO_CART", "", None, 7])
def test_unknown_action_rejects(name):
    assert run(prop(name="open_product").__class__(**{**prop().__dict__, "name": name})).reason == "unknown_action"


@pytest.mark.parametrize("over,reason", [
    ({"action_id": "bad"}, "invalid_action_id"), ({"action_id": None}, "invalid_action_id"),
    ({"session_id": ""}, "invalid_session"), ({"session_id": 5}, "invalid_session"),
    ({"params": "x"}, "invalid_params"), ({"params": {"product_id": "nope"}}, "invalid_params"),
    ({"params": {"product_id": P1, "extra": 1}}, "invalid_params"),
])
def test_malformed_input_rejects(over, reason):
    assert run(prop(**over)).reason == reason


@pytest.mark.parametrize("q", [0, -1, 1001, True, 1.5, "2", None])
def test_quantity_must_be_positive_bounded_int(q):
    assert run(prop("add_to_cart", params={**LINE, "quantity": q})).reason == "invalid_params"


def test_line_limits_and_shape():
    assert run(prop("start_whatsapp_order", params={"items": []})).reason == "invalid_params"
    assert run(prop("start_whatsapp_order", params={"items": [LINE] * 11})).reason == "invalid_params"
    assert run(prop("add_to_cart", params={**LINE, "variant_id": "x"})).reason == "invalid_params"


@pytest.mark.parametrize("junk", [None, "x", 3, {}, object()])
def test_non_proposal_and_bad_now_fail_closed(junk):
    assert k.validate(junk, k.InMemoryLedger(), NOW).outcome == "rejected"
    assert k.validate(prop(), k.InMemoryLedger(), "now").reason == "invalid_proposal"


def test_broken_ledger_fails_closed():
    assert k.validate(prop(), object(), NOW).reason == "invalid_state"


def test_replay_returns_same_decision_marked_replayed():
    ledger = k.InMemoryLedger()
    first, again = run(prop(), ledger), run(prop(), ledger)
    assert not first.replayed and again.replayed
    assert (again.outcome, again.fingerprint) == (first.outcome, first.fingerprint)


def test_same_id_different_params_conflicts():
    ledger = k.InMemoryLedger()
    run(prop(), ledger)
    d = run(prop(params={"product_id": P1}), ledger)
    assert (d.outcome, d.reason) == ("rejected", "idempotency_conflict")


def test_rejection_and_pending_are_not_recorded():
    ledger = k.InMemoryLedger()
    run(prop("add_to_cart"), ledger)
    run(prop(params="x"), ledger)
    assert ledger.get(SID, AID) is None


def test_ledger_is_per_session():
    ledger = k.InMemoryLedger()
    run(prop(), ledger)
    assert not run(prop(session_id="sess-2"), ledger).replayed


def test_expired_confirmation_rejects():
    p = prop("add_to_cart")
    d = run(prop("add_to_cart", confirmation=conf(p)), now=NOW + 60)
    assert d.reason == "confirmation_expired"


@pytest.mark.parametrize("over,reason", [
    ({"explicit": False}, "confirmation_invalid"), ({"explicit": "yes"}, "confirmation_invalid"),
    ({"expires_at": NOW + 301 + 10}, "confirmation_invalid"), ({"confirmed_at": NOW + 5}, "confirmation_invalid"),
    ({"expires_at": "soon"}, "confirmation_invalid"), ({"session_id": "other"}, "session_mismatch"),
    ({"action_id": "act_ffffffffffffffff"}, "confirmation_mismatch"), ({"fingerprint": "0" * 64}, "confirmation_mismatch"),
])
def test_bad_confirmation_rejects(over, reason):
    p = prop("add_to_cart")
    assert run(prop("add_to_cart", confirmation=conf(p, **over))).reason == reason


def test_confirmation_for_other_params_is_rejected():
    c = conf(prop("add_to_cart"))
    d = run(prop("add_to_cart", params={**LINE, "quantity": 9}, confirmation=c))
    assert d.reason == "confirmation_mismatch"


def test_non_confirmation_object_rejected():
    assert run(prop("add_to_cart", confirmation={"explicit": True})).reason == "confirmation_invalid"


def test_dropped_hard_constraint_rejects():
    p = prop("apply_filters", params={"filters": {"material": "wool"}})
    assert run(p).reason == "constraint_dropped"
    assert run(prop("show_products", params={"product_ids": [P1], "filters": {"colour": "blue"}})).reason == "constraint_dropped"


def test_relaxation_requires_acknowledgement():
    hard = {"hard": {"colour": "red"}, "relaxed": ["colour"]}
    p = prop("apply_filters", params={"filters": {"material": "wool"}}, constraints=hard)
    assert run(p).reason == "silent_relaxation"
    ok = prop("apply_filters", params={"filters": {"material": "wool"}},
              constraints={**hard, "relaxation_acknowledged": True})
    assert run(ok).outcome == "validated"


@pytest.mark.parametrize("c", [None, "x", {"hard": 1}, {"hard": {}, "relaxed": "colour"},
                               {"hard": {}, "relaxed": ["ghost"]}, {"hard": {}, "extra": 1},
                               {"hard": {}, "relaxation_acknowledged": "yes"}])
def test_malformed_constraints_reject(c):
    assert run(prop(constraints=c)).reason == "invalid_constraints"


def test_kernel_is_inert():
    d = run(prop("add_to_cart", confirmation=conf(prop("add_to_cart"))))
    assert d.executed is False
    assert not any(hasattr(k, n) for n in ("execute", "run", "add", "send", "requests", "httpx", "sqlalchemy"))
