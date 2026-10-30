"""M3-S1 validated action kernel: allowlist, context/permissions, current-state checks, idempotency, audit safety.
Fake in-memory catalogue only. The kernel validates proposals; it can never execute anything."""
import json
import socket
from pathlib import Path

import pytest

from actions import kernel as k

P1 = "11111111-1111-4111-8111-111111111111"
V1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
V2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
KEY = "idem_0123456789abcdef"
ALL = frozenset({"catalogue:read", "cart:propose", "enquiry:initiate"})


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def no_net(*a, **k_):
        raise AssertionError("network used")
    monkeypatch.setattr(socket, "socket", no_net)
    monkeypatch.setattr(socket, "create_connection", no_net)


def catalogue(**over):
    product = {
        "id": P1, "status": "active", "is_active": True, "revision": 7, "currency": "PKR", "price": 3500,
        "variants": [
            {"id": V1, "is_active": True, "price": 3500, "currency": "PKR", "stock": 5},
            {"id": V2, "is_active": True, "price": 3900, "currency": "PKR", "stock": 0},
        ],
    }
    product.update(over)
    return k.InMemoryCatalogue({P1: product})


def ctx(**over):
    base = {"session_id": "sess-secret-123", "user_id": "user-pii-42", "permissions": ALL}
    base.update(over)
    return k.ActionContext(**base)


def item(**over):
    base = {"product_id": P1, "variant_id": V1, "quantity": 2, "expected_revision": 7,
            "expected_unit_price": 3500, "currency": "PKR"}
    base.update(over)
    return base


_DEFAULT = object()


def cart(key=KEY, context=_DEFAULT, **over):
    return k.ActionProposal("add_to_cart", key, item(**over), ctx() if context is _DEFAULT else context)


def run(proposal, cat=None, ledger=None):
    return k.validate(proposal, cat or catalogue(), ledger if ledger is not None else k.IdempotencyLedger())


# --- happy paths
def test_display_reference_validates():
    d = run(k.ActionProposal("show_product", KEY, {"product_id": P1, "expected_revision": 7}, ctx()))
    assert (d.outcome, d.reason, d.executed, d.replayed) == ("validated", "ok", False, False)


def test_display_reference_with_variant():
    d = run(k.ActionProposal("show_product", KEY, {"product_id": P1, "variant_id": V1, "expected_revision": 7}, ctx()))
    assert d.outcome == "validated"


def test_add_to_cart_validates_and_never_executes():
    d = run(cart())
    assert (d.outcome, d.reason, d.executed) == ("validated", "ok", False)
    assert len(d.fingerprint) == 64


def test_whatsapp_enquiry_validates_multi_line():
    p = k.ActionProposal("start_whatsapp_enquiry", KEY, {"items": [item(), item(quantity=1)]}, ctx())
    assert run(p).outcome == "validated"


# --- unknown / unsafe actions
@pytest.mark.parametrize("name", ["checkout", "place_order", "pay", "send_whatsapp", "delete_product", "", "ADD_TO_CART",
                                  None, 7, "add_to_cart; drop table"])
def test_unknown_or_unsafe_action_rejects(name):
    d = run(k.ActionProposal(name, KEY, item(), ctx()))
    assert (d.outcome, d.reason) == ("rejected", "unknown_action")


def test_allowlist_is_exactly_three():
    assert {a.value for a in k.ActionType} == {"show_product", "add_to_cart", "start_whatsapp_enquiry"}


# --- context / permissions
@pytest.mark.parametrize("context", [None, "x", {"session_id": "s"}])
def test_missing_or_malformed_context_rejects(context):
    assert run(cart(context=context)).reason == "missing_context"


@pytest.mark.parametrize("sid", ["", None, "x" * 129, "has space", "bad\nnewline", 5])
def test_invalid_session_rejects(sid):
    assert run(cart(context=ctx(session_id=sid))).reason == "missing_context"


def test_invalid_user_id_rejects_but_anonymous_is_allowed():
    assert run(cart(context=ctx(user_id="bad id!"))).reason == "missing_context"
    assert run(cart(context=ctx(user_id=None))).outcome == "validated"


@pytest.mark.parametrize("action,params,perm", [
    ("show_product", {"product_id": P1, "expected_revision": 7}, "catalogue:read"),
    ("add_to_cart", item(), "cart:propose"),
    ("start_whatsapp_enquiry", {"items": [item()]}, "enquiry:initiate"),
])
def test_permission_is_per_action(action, params, perm):
    d = run(k.ActionProposal(action, KEY, params, ctx(permissions=ALL - {perm})))
    assert (d.outcome, d.reason) == ("rejected", "permission_denied")
    only = run(k.ActionProposal(action, KEY, params, ctx(permissions=frozenset({perm}))))
    assert only.outcome == "validated"


def test_permissions_must_be_a_collection_of_strings():
    assert run(cart(context=ctx(permissions="cart:propose"))).reason == "missing_context"


# --- state checks
def test_stale_revision_rejects():
    assert run(cart(expected_revision=6)).reason == "stale_revision"
    p = k.ActionProposal("show_product", KEY, {"product_id": P1, "expected_revision": 6}, ctx())
    assert run(p).reason == "stale_revision"


def test_stale_price_rejects():
    assert run(cart(expected_unit_price=3000)).reason == "stale_price"


def test_price_changed_in_catalogue_rejects():
    cat = catalogue(revision=7)
    cat.products[P1]["variants"][0]["price"] = 4000
    assert run(cart(), cat).reason == "stale_price"


def test_out_of_stock_rejects():
    assert run(cart(variant_id=V2, expected_unit_price=3900)).reason == "out_of_stock"


def test_insufficient_stock_rejects_and_exact_stock_passes():
    assert run(cart(quantity=6)).reason == "insufficient_stock"
    assert run(cart(quantity=5)).outcome == "validated"


def test_unknown_product_and_variant_reject():
    assert run(cart(product_id="22222222-2222-4222-8222-222222222222")).reason == "product_not_found"
    assert run(cart(variant_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc")).reason == "variant_not_found"


@pytest.mark.parametrize("over", [{"status": "draft", "is_active": False}, {"status": "archived", "is_active": False},
                                  {"status": "active", "is_active": False}])
def test_non_public_product_rejects(over):
    assert run(cart(), catalogue(**over)).reason == "product_unavailable"


def test_inactive_variant_rejects():
    cat = catalogue()
    cat.products[P1]["variants"][0]["is_active"] = False
    assert run(cart(), cat).reason == "variant_unavailable"


def test_whatsapp_rejects_if_any_line_is_bad():
    p = k.ActionProposal("start_whatsapp_enquiry", KEY, {"items": [item(), item(quantity=99)]}, ctx())
    assert run(p).reason == "insufficient_stock"


# --- quantity / currency / structure
@pytest.mark.parametrize("q", [0, -1, 1001, 1.5, "2", None, True])
def test_invalid_quantity_rejects(q):
    assert run(cart(quantity=q)).reason == "invalid_quantity"


@pytest.mark.parametrize("c", ["pkr", "USD", "PK", "", None, 5, "PKR "])
def test_invalid_or_unsupported_currency_rejects(c):
    assert run(cart(currency=c)).reason == "invalid_currency"


def test_currency_mismatch_with_catalogue_rejects():
    cat = catalogue()
    cat.products[P1]["variants"][0]["currency"] = "AED"
    assert run(cart(), cat).reason == "currency_mismatch"


@pytest.mark.parametrize("params", [
    {**item(), "extra": 1}, {k_: v for k_, v in item().items() if k_ != "variant_id"}, {**item(), "product_id": "nope"},
    {**item(), "expected_revision": 0}, {**item(), "expected_revision": True}, {**item(), "expected_unit_price": -1},
    {**item(), "expected_unit_price": 1.5}, "not-a-mapping",
])
def test_invalid_params_reject(params):
    assert run(k.ActionProposal("add_to_cart", KEY, params, ctx())).reason in {"invalid_params", "invalid_quantity", "invalid_currency"}
    assert run(k.ActionProposal("add_to_cart", KEY, params, ctx())).outcome == "rejected"


@pytest.mark.parametrize("items", [[], "x", [item()] * 11, [item(), "x"], None])
def test_whatsapp_items_must_be_a_bounded_list(items):
    assert run(k.ActionProposal("start_whatsapp_enquiry", KEY, {"items": items}, ctx())).reason == "invalid_params"


# --- idempotency
@pytest.mark.parametrize("key", ["", "short", "idem_", "idem_ has space 0123456", "x" * 80, "IDEM_0123456789abcdef", None, 5,
                                 "idem_" + "a" * 65, "idem_0123456789abc\n"])
def test_invalid_idempotency_key_rejects(key):
    assert run(cart(key=key)).reason == "invalid_idempotency_key"


def test_fingerprint_is_deterministic_and_key_order_independent():
    a = run(cart()).fingerprint
    b = run(k.ActionProposal("add_to_cart", "idem_ffffffffffffffff", dict(reversed(list(item().items()))), ctx())).fingerprint
    assert a == b
    assert run(cart(quantity=3)).fingerprint != a
    assert run(cart(context=ctx(session_id="other-session"))).fingerprint != a


def test_duplicate_with_same_request_replays_original_decision():
    ledger = k.IdempotencyLedger()
    first = run(cart(), ledger=ledger)
    again = run(cart(), ledger=ledger)
    assert (again.outcome, again.reason, again.replayed) == ("validated", "ok", True)
    assert again.fingerprint == first.fingerprint


def test_replay_does_not_reread_state():
    ledger = k.IdempotencyLedger()
    run(cart(), ledger=ledger)
    assert run(cart(), catalogue(revision=99), ledger).replayed is True


def test_same_key_different_request_conflicts():
    ledger = k.IdempotencyLedger()
    run(cart(), ledger=ledger)
    d = run(cart(quantity=3), ledger=ledger)
    assert (d.outcome, d.reason) == ("rejected", "idempotency_conflict")
    assert d.replayed is False


def test_same_key_different_action_conflicts():
    ledger = k.IdempotencyLedger()
    run(cart(), ledger=ledger)
    p = k.ActionProposal("start_whatsapp_enquiry", KEY, {"items": [item()]}, ctx())
    assert run(p, ledger=ledger).reason == "idempotency_conflict"


def test_keys_are_scoped_per_session():
    ledger = k.IdempotencyLedger()
    run(cart(), ledger=ledger)
    other = run(cart(quantity=3, context=ctx(session_id="sess-other")), ledger=ledger)
    assert other.outcome == "validated" and not other.replayed


def test_rejections_are_not_recorded_so_a_corrected_retry_is_possible():
    ledger = k.IdempotencyLedger()
    assert run(cart(expected_revision=1), ledger=ledger).reason == "stale_revision"
    assert run(cart(), ledger=ledger).outcome == "validated"


# --- audit safety
def test_audit_record_is_redacted_and_deterministic():
    d = run(cart())
    rec = d.audit()
    text = json.dumps(rec)
    for secret in ("sess-secret-123", "user-pii-42"):
        assert secret not in text
    assert rec == run(cart()).audit()
    assert rec["action_type"] == "add_to_cart" and rec["outcome"] == "validated" and rec["executed"] is False
    assert rec["fingerprint"] == d.fingerprint and rec["idempotency_key"] == KEY
    assert rec["product_ids"] == [P1] and rec["variant_ids"] == [V1] and rec["quantity_total"] == 2
    assert len(rec["session_ref"]) == 16 and rec["has_user"] is True


def test_audit_never_echoes_untrusted_input():
    evil = "checkout token=sk-live-SECRET alice@example.test 03001234567"
    d = run(k.ActionProposal(evil, "idem_" + "z" * 16, {"note": evil}, ctx()))
    text = json.dumps(d.audit())
    assert "SECRET" not in text and "alice" not in text and "0300" not in text
    assert d.audit()["action_type"] == "unknown"
    bad = run(cart(key=evil))
    assert "SECRET" not in json.dumps(bad.audit()) and bad.audit()["idempotency_key"] is None


def test_audit_for_rejection_has_reason_and_no_params():
    rec = run(cart(expected_unit_price=1)).audit()
    assert (rec["outcome"], rec["reason"]) == ("rejected", "stale_price")
    assert "expected_unit_price" not in json.dumps(rec) and "params" not in rec


def test_audit_keys_are_a_fixed_set():
    assert set(run(cart()).audit()) == {"version", "action_type", "outcome", "reason", "executed", "replayed", "fingerprint",
                                         "idempotency_key", "session_ref", "has_user", "product_ids", "variant_ids", "quantity_total"}


def test_decision_is_immutable():
    d = run(cart())
    with pytest.raises(Exception):
        d.outcome = "rejected"


# --- no execution surface
def test_module_has_no_execution_surface_or_external_imports():
    src = Path(k.__file__).read_text()
    for banned in ("import requests", "import httpx", "import socket", "import subprocess", "import urllib", "import aiohttp",
                   "wa.me", "whatsapp.com", "openai", "anthropic", "sqlalchemy", "import os"):
        assert banned not in src, banned
    public = [n for n in dir(k) if not n.startswith("_")]
    assert not [n for n in public if any(w in n.lower() for w in ("execute", "dispatch", "send", "checkout", "pay", "commit"))]


# --- hostile boundary: malformed anything => deterministic rejection, never an exception
class _Boom:
    def get(self, *_):
        raise RuntimeError("db password=hunter2")


def _assert_safe_reject(d, reason):
    assert (d.outcome, d.reason, d.executed) == ("rejected", reason, False)
    rec = d.audit()
    assert set(rec) == set(run(cart()).audit())
    assert "hunter2" not in json.dumps(rec) and "sess-secret-123" not in json.dumps(rec)
    assert run_again_equal(d)


def run_again_equal(d):
    return d.audit() == d.audit()


@pytest.mark.parametrize("bad", [None, 0, 7, "add_to_cart", b"x", [], (), {}, {"action_type": "add_to_cart"}, object(),
                                 type("Fake", (), {"action_type": "add_to_cart"})()])
def test_non_proposal_objects_reject(bad):
    _assert_safe_reject(k.validate(bad, catalogue(), k.IdempotencyLedger()), "invalid_proposal")


@pytest.mark.parametrize("params", [None, 5, "x", [], [item()], {"items": None}, {"items": [None]}, {"items": [[]]},
                                    {"items": {"a": 1}}, item(product_id=None), item(variant_id=5), item(quantity=[1]),
                                    item(quantity={"a": 1}), item(currency=["PKR"]), item(expected_revision="7"),
                                    item(expected_unit_price=object()), {}])
@pytest.mark.parametrize("action", ["add_to_cart", "start_whatsapp_enquiry", "show_product"])
def test_malformed_params_reject_never_raise(action, params):
    d = run(k.ActionProposal(action, KEY, params, ctx()))
    assert d.outcome == "rejected" and d.executed is False
    json.dumps(d.audit())


@pytest.mark.parametrize("context", [None, 5, "s", {}, {"session_id": "s", "permissions": ALL}, object(),
                                     ctx(permissions=[["x"]]), ctx(permissions=None), ctx(session_id=None), ctx(user_id=5)])
def test_malformed_context_rejects(context):
    assert run(cart(context=context)).reason == "missing_context"


@pytest.mark.parametrize("key", [None, 5, [], {}, b"idem_0123456789abcdef"])
def test_malformed_key_rejects(key):
    assert run(cart(key=key)).reason == "invalid_idempotency_key"


@pytest.mark.parametrize("state", [None, 5, _Boom(), k.InMemoryCatalogue({P1: None}), k.InMemoryCatalogue({P1: 5}),
                                   k.InMemoryCatalogue({P1: {"status": "active", "is_active": True, "revision": 7, "variants": 5}}),
                                   k.InMemoryCatalogue({P1: {"status": "active", "is_active": True, "revision": 7, "variants": [None, 3]}})])
def test_malformed_catalogue_state_rejects_without_leaking(state):
    d = k.validate(cart(), state, k.IdempotencyLedger())
    assert d.outcome == "rejected" and d.executed is False
    assert "hunter2" not in json.dumps(d.audit()) and "RuntimeError" not in json.dumps(d.audit())


def test_broken_ledger_rejects_and_is_not_validated():
    d = k.validate(cart(), catalogue(), None)
    _assert_safe_reject(d, "invalid_state")


def test_kernel_version_bumped_for_rejection_rule_change():
    assert k.KERNEL_VERSION == 2 and run(cart()).audit()["version"] == 2
