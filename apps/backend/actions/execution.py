"""M3-S3 execution boundary: turns a *confirmed* kernel-validated proposal into a browser-consumable intent. Nothing is sent or ordered.

Every call re-runs the M3-S1 kernel (fresh ledger, current clock) and verifies the lines against the live catalogue.
add_to_cart returns normalized lines for the client-side cart (localStorage) to apply; start_whatsapp_order returns an inert
handoff intent (sent=False, order_confirmed=False): this checkout has no server-side enquiry verifier, so the existing client
cart/WhatsApp flow stays the only path. Replay is bound to (session_id, action_id) + fingerprint in an atomic store.
"""
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from actions import kernel as k

EXECUTABLE = frozenset({"add_to_cart", "start_whatsapp_order"})


@dataclass(frozen=True)
class Outcome:
    status: str  # executed | rejected
    reason: str  # "ok" or a fixed code
    replayed: bool = False
    action: str = "unknown"
    action_id: str | None = None
    result: dict | None = None


class Store(Protocol):
    async def claim(self, session_id: str, action_id: str, fingerprint: str, action: str, result: dict) -> tuple[str, dict, bool]:
        """Atomically store (fingerprint, result) unless the key exists; return what is stored and whether this call created it."""


class MemoryStore:
    """Bounded (oldest evicted), single-process. Used by tests; production uses PgStore."""

    def __init__(self, max_entries: int = 10_000):
        self._rows: OrderedDict[tuple[str, str], tuple[str, dict]] = OrderedDict()
        self._max = max_entries

    async def claim(self, session_id, action_id, fingerprint, action, result):
        key = (session_id, action_id)
        created = key not in self._rows  # no await between check and set: atomic on one loop
        row = self._rows.setdefault(key, (fingerprint, result))
        while len(self._rows) > self._max:
            self._rows.popitem(last=False)
        return (*row, created)


class PgStore:
    """action_executions (migration 0010). The caller owns the transaction."""

    def __init__(self, session: AsyncSession):
        self._s = session

    async def claim(self, session_id, action_id, fingerprint, action, result):
        created = (await self._s.execute(text(
            "INSERT INTO action_executions (session_id, action_id, fingerprint, action, result) "
            "VALUES (:s, :a, :f, :n, CAST(:r AS jsonb)) ON CONFLICT (session_id, action_id) DO NOTHING RETURNING 1"),
            {"s": session_id, "a": action_id, "f": fingerprint, "n": action, "r": json.dumps(result)})).first() is not None
        row = (await self._s.execute(text(
            "SELECT fingerprint, result FROM action_executions WHERE session_id = :s AND action_id = :a"),
            {"s": session_id, "a": action_id})).one()
        return row[0], row[1], created


def _lines(name: str, params: dict) -> list[dict]:
    return params["items"] if name == "start_whatsapp_order" else [params]


def intent(name: str, action_id: str, lines: list[dict]) -> dict:
    if name == "add_to_cart":
        return {"type": "add_to_cart", "action_id": action_id, "items": lines, "applied_by": "client_cart"}
    return {"type": "start_whatsapp_order", "action_id": action_id, "items": lines, "sent": False,
            "order_confirmed": False, "next": "client_whatsapp_handoff"}


async def execute(proposal: k.ActionProposal, *, store: Store, check_lines: Callable[[list[dict]], Awaitable[bool]],
                  now: float | None = None) -> Outcome:
    d = k.validate(proposal, k.InMemoryLedger(), time.time() if now is None else now)
    base = {"action": d.action, "action_id": d.action_id}
    if d.outcome == "needs_confirmation":
        return Outcome("rejected", "confirmation_required", **base)
    if d.outcome != "validated":
        return Outcome("rejected", d.reason, **base)
    if d.action not in EXECUTABLE:
        return Outcome("rejected", "unsupported_action", **base)
    # Normalised by the kernel's fingerprint inputs; re-normalise the same way for the output lines.
    params = k._normalise(d.action, proposal.params)
    lines = _lines(d.action, params)
    if not await check_lines(lines):
        return Outcome("rejected", "unavailable_item", **base)
    fp, stored, created = await store.claim(proposal.session_id, d.action_id, d.fingerprint, d.action,
                                            {"intent": intent(d.action, d.action_id, lines), "acknowledged": True})
    if fp != d.fingerprint:
        return Outcome("rejected", "idempotency_conflict", **base)
    return Outcome("executed", "ok", replayed=not created, **base, result=stored)


async def lines_available(session: AsyncSession, lines: list[dict]) -> bool:
    """Every line's variant belongs to the product, both publicly visible and the variant active."""
    for line in lines:
        ok = (await session.execute(text(
            "SELECT 1 FROM variants v JOIN products p ON p.id = v.product_id WHERE v.id = :v AND p.id = :p "
            "AND v.is_active AND p.is_active AND p.status = 'active'"),
            {"v": line["variant_id"], "p": line["product_id"]})).first()
        if not ok:
            return False
    return True
