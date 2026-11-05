"""Pure action kernel: decides whether a proposed storefront action is acceptable. Never performs one.

No I/O, network, DB, cart, WhatsApp or clock: callers pass `now` (epoch seconds) and an in-memory ledger.
Outcomes: `validated` (acceptable now), `needs_confirmation` (add_to_cart / start_whatsapp_order without a valid
explicit confirmation) or `rejected` with a fixed reason code. `executed` is always False.
(shortcut: in-memory ledger; a durable one needs its own reviewed change.)
"""
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

KERNEL_VERSION = 1
ACTIONS = frozenset({"show_products", "open_product", "apply_filters", "add_to_cart", "start_whatsapp_order"})
CONFIRMATION_REQUIRED = frozenset({"add_to_cart", "start_whatsapp_order"})
MAX_QUANTITY = 1000  # same bound as POST /v1/enquiries
MAX_LINES = 10
MAX_PRODUCTS = 24
MAX_CONFIRMATION_TTL = 300  # seconds
_ID = re.compile(r"^act_[A-Za-z0-9_-]{16,64}$")
_REF = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


@dataclass(frozen=True)
class Confirmation:
    """Explicit user confirmation bound to one action id, session and params fingerprint."""
    action_id: Any
    session_id: Any
    fingerprint: Any
    confirmed_at: Any
    expires_at: Any
    explicit: Any = False


@dataclass(frozen=True)
class ActionProposal:
    action_id: Any
    name: Any
    session_id: Any
    params: Any
    constraints: Any  # {"hard": {key: value}, "relaxed": [key, ...], "relaxation_acknowledged": bool}
    confirmation: Any = None


@dataclass(frozen=True)
class Decision:
    outcome: str  # validated | needs_confirmation | rejected
    reason: str
    action: str  # allowlisted name, else "unknown"
    action_id: str | None = None
    fingerprint: str | None = None
    replayed: bool = False
    executed: bool = False  # always False: the kernel has no execution path


class InMemoryLedger:
    """Remembers validated decisions per (session, action id). Rejections are not stored."""

    def __init__(self):
        self._seen: dict[tuple[str, str], Decision] = {}

    def get(self, session_id: str, action_id: str) -> Decision | None:
        return self._seen.get((session_id, action_id))

    def put(self, session_id: str, action_id: str, decision: Decision) -> None:
        self._seen[(session_id, action_id)] = decision


class _Reject(Exception):
    pass


def _int(v, lo, hi) -> int:
    if not (isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi):
        raise _Reject("invalid_params")
    return v


def _uuid(v) -> str:
    if not (isinstance(v, str) and _UUID.match(v)):
        raise _Reject("invalid_params")
    return v


def _scalar(v) -> bool:
    return (isinstance(v, str) and 0 < len(v) <= 64) or (isinstance(v, int) and not isinstance(v, bool))


def _filters(f) -> dict:
    if not isinstance(f, Mapping) or not f or len(f) > 20:
        raise _Reject("invalid_params")
    for k, v in f.items():
        ok = _scalar(v) or (isinstance(v, (list, tuple)) and 0 < len(v) <= 20 and all(_scalar(x) for x in v))
        if not (isinstance(k, str) and _REF.match(k) and ok):
            raise _Reject("invalid_params")
    return {k: list(v) if isinstance(v, (list, tuple)) else v for k, v in f.items()}


def _line(raw) -> dict:
    if not isinstance(raw, Mapping) or set(raw) != {"product_id", "variant_id", "quantity"}:
        raise _Reject("invalid_params")
    return {"product_id": _uuid(raw["product_id"]), "variant_id": _uuid(raw["variant_id"]),
            "quantity": _int(raw["quantity"], 1, MAX_QUANTITY)}


def _normalise(name: str, p) -> dict:
    if not isinstance(p, Mapping):
        raise _Reject("invalid_params")
    keys = set(p)
    if name == "show_products":
        ids = p.get("product_ids")
        if keys - {"product_ids", "filters"} or not isinstance(ids, (list, tuple)) or not 1 <= len(ids) <= MAX_PRODUCTS:
            raise _Reject("invalid_params")
        out = {"product_ids": [_uuid(i) for i in ids]}
        if "filters" in p:
            out["filters"] = _filters(p["filters"])
        return out
    if name == "open_product":
        if "product_id" not in keys or keys - {"product_id", "variant_id"}:
            raise _Reject("invalid_params")
        out = {"product_id": _uuid(p["product_id"])}
        if "variant_id" in p:
            out["variant_id"] = _uuid(p["variant_id"])
        return out
    if name == "apply_filters":
        if keys != {"filters"}:
            raise _Reject("invalid_params")
        return {"filters": _filters(p["filters"])}
    if name == "add_to_cart":
        return _line(p)
    items = p.get("items")  # start_whatsapp_order
    if keys != {"items"} or not isinstance(items, (list, tuple)) or not 1 <= len(items) <= MAX_LINES:
        raise _Reject("invalid_params")
    return {"items": [_line(i) for i in items]}


def _check_constraints(name: str, c, params: dict) -> None:
    """Hard constraints must reach the action unchanged; relaxing one needs an explicit acknowledgement."""
    if not isinstance(c, Mapping) or set(c) - {"hard", "relaxed", "relaxation_acknowledged"}:
        raise _Reject("invalid_constraints")
    hard, relaxed, ack = c.get("hard"), c.get("relaxed", ()), c.get("relaxation_acknowledged", False)
    if not isinstance(hard, Mapping) or not isinstance(ack, bool) or not isinstance(relaxed, (list, tuple)):
        raise _Reject("invalid_constraints")
    if not all(isinstance(r, str) and r in hard for r in relaxed):
        raise _Reject("invalid_constraints")
    if relaxed and not ack:
        raise _Reject("silent_relaxation")
    if name in ("show_products", "apply_filters"):
        filters = params.get("filters", {})
        if any(k not in relaxed and filters.get(k) != _filters({k: v})[k] for k, v in hard.items()):
            raise _Reject("constraint_dropped")


def _fingerprint(name: str, session_id: str, params: dict) -> str:
    blob = json.dumps({"a": name, "s": session_id, "p": params}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _check_confirmation(c, action_id: str, session_id: str, fp: str, now) -> None:
    if c is None:
        raise _Reject("needs_confirmation")
    if not isinstance(c, Confirmation) or c.explicit is not True:
        raise _Reject("confirmation_invalid")
    nums = (c.confirmed_at, c.expires_at)
    if not all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in nums):
        raise _Reject("confirmation_invalid")
    if c.session_id != session_id:
        raise _Reject("session_mismatch")
    if c.action_id != action_id or c.fingerprint != fp:
        raise _Reject("confirmation_mismatch")
    if not (c.confirmed_at <= now and 0 < c.expires_at - c.confirmed_at <= MAX_CONFIRMATION_TTL):
        raise _Reject("confirmation_invalid")
    if now >= c.expires_at:
        raise _Reject("confirmation_expired")


def validate(proposal: ActionProposal, ledger: InMemoryLedger, now: float) -> Decision:
    """Deterministic for the same proposal, ledger state and `now`. Only validated decisions are recorded."""
    base: dict[str, Any] = {"action": "unknown"}
    try:
        if not isinstance(proposal, ActionProposal) or isinstance(now, bool) or not isinstance(now, (int, float)):
            raise _Reject("invalid_proposal")
        name = proposal.name
        if not (isinstance(name, str) and name in ACTIONS):
            raise _Reject("unknown_action")
        base["action"] = name
        aid, sid = proposal.action_id, proposal.session_id
        if not (isinstance(aid, str) and _ID.match(aid)):
            raise _Reject("invalid_action_id")
        base["action_id"] = aid
        if not (isinstance(sid, str) and _REF.match(sid)):
            raise _Reject("invalid_session")
        params = _normalise(name, proposal.params)
        _check_constraints(name, proposal.constraints, params)
        base["fingerprint"] = fp = _fingerprint(name, sid, params)
        prior = ledger.get(sid, aid)
        if prior is not None:
            if prior.fingerprint != fp:
                raise _Reject("idempotency_conflict")
            return Decision(**{**prior.__dict__, "replayed": True})
        if name in CONFIRMATION_REQUIRED:
            try:
                _check_confirmation(proposal.confirmation, aid, sid, fp, now)
            except _Reject as r:
                if str(r) == "needs_confirmation":
                    return Decision("needs_confirmation", "confirmation_required", **base)
                raise
        decision = Decision("validated", "ok", **base)
        ledger.put(sid, aid, decision)
        return decision
    except _Reject as r:
        return Decision("rejected", str(r), **base)
    except Exception:  # fail closed on malformed input/ledger; never echo error text
        return Decision("rejected", "invalid_state", **base)
