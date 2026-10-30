"""Validated action kernel: decides whether an assistant-proposed action is acceptable. Never performs one.

A proposal (typed, allowlisted) is checked against the caller's context and permissions, the *current* catalogue state
(revision, price, currency, stock, visibility) and an idempotency ledger. The result is an immutable `Decision`
(`validated` or `rejected` with a fixed reason code) plus an audit-safe record. `validated` only means "this exact request
is currently acceptable"; carting, WhatsApp, orders and payments stay in their existing, separately confirmed paths, and
this module has no I/O, network, DB or clock. Bump KERNEL_VERSION on any change to the rules below.
(shortcut: in-memory ledger and catalogue; a durable ledger needs its own reviewed change and migration.)
"""
import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol

KERNEL_VERSION = 1
SUPPORTED_CURRENCIES = frozenset({"PKR"})
MAX_QUANTITY = 1000  # same bound as POST /v1/enquiries
MAX_LINES = 10
_KEY = re.compile(r"^idem_[A-Za-z0-9_-]{16,64}$")
_REF = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_ITEM_FIELDS = frozenset({"product_id", "variant_id", "quantity", "expected_revision", "expected_unit_price", "currency"})


class ActionType(str, Enum):
    SHOW_PRODUCT = "show_product"
    ADD_TO_CART = "add_to_cart"
    START_WHATSAPP_ENQUIRY = "start_whatsapp_enquiry"


PERMISSION = {
    ActionType.SHOW_PRODUCT: "catalogue:read",
    ActionType.ADD_TO_CART: "cart:propose",
    ActionType.START_WHATSAPP_ENQUIRY: "enquiry:initiate",
}


@dataclass(frozen=True)
class ActionContext:
    session_id: Any
    permissions: Any
    user_id: Any = None  # None = anonymous visitor


@dataclass(frozen=True)
class ActionProposal:
    action_type: Any
    idempotency_key: Any
    params: Any
    context: Any


class CatalogueState(Protocol):
    def get(self, product_id: str) -> Mapping[str, Any] | None: ...


@dataclass
class InMemoryCatalogue:
    """Fake current state: {product_id: {status, is_active, revision, variants: [{id, is_active, price, currency, stock}]}}."""
    products: dict = field(default_factory=dict)

    def get(self, product_id: str):
        return self.products.get(product_id)


@dataclass(frozen=True)
class Decision:
    outcome: str  # validated | rejected
    reason: str  # "ok" or a fixed reason code
    action_type: str  # allowlisted name, else "unknown"
    fingerprint: str | None = None
    idempotency_key: str | None = None
    replayed: bool = False
    session_ref: str | None = None
    has_user: bool = False
    product_ids: tuple = ()
    variant_ids: tuple = ()
    quantity_total: int = 0
    executed: bool = False  # always False: the kernel has no execution path

    def audit(self) -> dict:
        """Fixed-shape record: opaque ids and codes only; never raw session/user ids, params or caller text."""
        return {
            "version": KERNEL_VERSION, "action_type": self.action_type, "outcome": self.outcome, "reason": self.reason,
            "executed": False, "replayed": self.replayed, "fingerprint": self.fingerprint,
            "idempotency_key": self.idempotency_key, "session_ref": self.session_ref, "has_user": self.has_user,
            "product_ids": list(self.product_ids), "variant_ids": list(self.variant_ids),
            "quantity_total": self.quantity_total,
        }


class IdempotencyLedger:
    """Remembers *validated* decisions per (session, key). Rejections are not stored so a corrected retry can reuse the key."""

    def __init__(self):
        self._seen: dict[tuple[str, str], Decision] = {}

    def get(self, session_id: str, key: str) -> Decision | None:
        return self._seen.get((session_id, key))

    def put(self, session_id: str, key: str, decision: Decision) -> None:
        self._seen[(session_id, key)] = decision


class _Reject(Exception):
    pass


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _check_context(ctx) -> None:
    perms = getattr(ctx, "permissions", None)
    uid = getattr(ctx, "user_id", None)
    if not isinstance(ctx, ActionContext) or not (isinstance(ctx.session_id, str) and _REF.match(ctx.session_id)):
        raise _Reject("missing_context")
    if not isinstance(perms, (set, frozenset, tuple, list)) or not all(isinstance(p, str) for p in perms):
        raise _Reject("missing_context")
    if uid is not None and not (isinstance(uid, str) and _REF.match(uid)):
        raise _Reject("missing_context")


def _uuid(v) -> str:
    if not (isinstance(v, str) and _UUID.match(v)):
        raise _Reject("invalid_params")
    return v


def _item(raw) -> dict:
    if not isinstance(raw, Mapping) or set(raw) != _ITEM_FIELDS:
        raise _Reject("invalid_params")
    q = raw["quantity"]
    if not _is_int(q) or not 1 <= q <= MAX_QUANTITY:
        raise _Reject("invalid_quantity")
    c = raw["currency"]
    if not isinstance(c, str) or c not in SUPPORTED_CURRENCIES:
        raise _Reject("invalid_currency")
    rev, price = raw["expected_revision"], raw["expected_unit_price"]
    if not (_is_int(rev) and rev >= 1 and _is_int(price) and price >= 0):
        raise _Reject("invalid_params")
    return {"product_id": _uuid(raw["product_id"]), "variant_id": _uuid(raw["variant_id"]), "quantity": q,
            "expected_revision": rev, "expected_unit_price": price, "currency": c}


def _normalise(action: ActionType, params) -> dict:
    if not isinstance(params, Mapping):
        raise _Reject("invalid_params")
    if action is ActionType.ADD_TO_CART:
        return {"items": [_item(params)]}
    if action is ActionType.START_WHATSAPP_ENQUIRY:
        items = params.get("items")
        if set(params) != {"items"} or not isinstance(items, list) or not 1 <= len(items) <= MAX_LINES:
            raise _Reject("invalid_params")
        return {"items": [_item(i) for i in items]}
    if not set(params) <= {"product_id", "variant_id", "expected_revision"} or not {"product_id", "expected_revision"} <= set(params):
        raise _Reject("invalid_params")
    rev = params["expected_revision"]
    if not (_is_int(rev) and rev >= 1):
        raise _Reject("invalid_params")
    out = {"product_id": _uuid(params["product_id"]), "expected_revision": rev}
    if "variant_id" in params:
        out["variant_id"] = _uuid(params["variant_id"])
    return out


def _check_state(state: CatalogueState, line: Mapping, priced: bool) -> None:
    product = state.get(line["product_id"])
    if product is None:
        raise _Reject("product_not_found")
    if product.get("status") != "active" or product.get("is_active") is not True:  # public visibility rule
        raise _Reject("product_unavailable")
    if product.get("revision") != line["expected_revision"]:
        raise _Reject("stale_revision")
    if "variant_id" not in line:
        return
    variant = next((v for v in product.get("variants", ()) if v.get("id") == line["variant_id"]), None)
    if variant is None:
        raise _Reject("variant_not_found")
    if variant.get("is_active") is not True:
        raise _Reject("variant_unavailable")
    if not priced:
        return
    if variant.get("currency") != line["currency"]:
        raise _Reject("currency_mismatch")
    if variant.get("price") != line["expected_unit_price"]:
        raise _Reject("stale_price")
    stock = variant.get("stock")
    if not _is_int(stock) or stock < 1:
        raise _Reject("out_of_stock")
    if line["quantity"] > stock:
        raise _Reject("insufficient_stock")


def _fingerprint(action: ActionType, session_id: str, params: dict) -> str:
    blob = json.dumps({"a": action.value, "s": session_id, "p": params}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def validate(proposal: ActionProposal, state: CatalogueState, ledger: IdempotencyLedger) -> Decision:
    """Deterministic: same proposal + same state + same ledger => same Decision. Only records validated decisions."""
    base: dict[str, Any] = {"action_type": "unknown"}

    def reject(reason: str) -> Decision:
        return Decision("rejected", reason, **base)

    try:
        _check_context(proposal.context)
        ctx = proposal.context
        base.update(session_ref=hashlib.sha256(ctx.session_id.encode()).hexdigest()[:16], has_user=ctx.user_id is not None)
        try:
            action = ActionType(proposal.action_type) if isinstance(proposal.action_type, str) else None
        except ValueError:
            action = None
        if action is None:
            raise _Reject("unknown_action")
        base["action_type"] = action.value
        if PERMISSION[action] not in ctx.permissions:
            raise _Reject("permission_denied")
        key = proposal.idempotency_key
        if not (isinstance(key, str) and _KEY.match(key)):
            raise _Reject("invalid_idempotency_key")
        base["idempotency_key"] = key
        params = _normalise(action, proposal.params)
        lines = params.get("items", [params])
        base.update(product_ids=tuple(dict.fromkeys(l["product_id"] for l in lines)),
                    variant_ids=tuple(dict.fromkeys(l["variant_id"] for l in lines if "variant_id" in l)),
                    quantity_total=sum(l.get("quantity", 0) for l in lines))
        base["fingerprint"] = fp = _fingerprint(action, ctx.session_id, params)
        prior = ledger.get(ctx.session_id, key)
        if prior is not None:
            if prior.fingerprint != fp:
                raise _Reject("idempotency_conflict")
            return Decision(**{**prior.__dict__, "replayed": True})
        for line in lines:
            _check_state(state, line, priced=action is not ActionType.SHOW_PRODUCT)
    except _Reject as r:
        return reject(str(r))
    decision = Decision("validated", "ok", **base)
    ledger.put(ctx.session_id, key, decision)
    return decision
