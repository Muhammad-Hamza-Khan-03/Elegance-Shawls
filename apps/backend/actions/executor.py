"""M3-S3 execution adapters for add_to_cart and start_whatsapp_enquiry: runs only on an explicit user confirmation.

Every call re-runs the M3-S1 kernel against the *current* catalogue with a throwaway ledger (nothing cached from the model
turn is trusted), then performs the action through the injected `perform` callable. Executions are idempotent per
(session, key): a repeat with the same request returns the stored result, a different request under the same key conflicts,
and a failed attempt is not recorded so the user can retry. Audit records are fixed-shape: hashed session ref, opaque ids,
codes and the enquiry reference only; never raw ids, params, prices or exception text.
(shortcut: in-memory ledger, one global lock; per-process, so multiple workers can duplicate an enquiry reference, which
has no order, payment or stock effect. A durable ledger needs its own reviewed migration.)
"""
import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from actions import kernel as k

EXECUTABLE = frozenset({k.ActionType.ADD_TO_CART, k.ActionType.START_WHATSAPP_ENQUIRY})
log = logging.getLogger("elegance.actions")


@dataclass(frozen=True)
class Execution:
    outcome: str  # executed | rejected
    reason: str  # "ok" or a fixed reason code
    replayed: bool = False
    result: dict | None = None
    action_type: str = "unknown"


class ExecutionLedger:
    def __init__(self, max_entries: int = 10_000):
        self.lock = asyncio.Lock()
        self._done: OrderedDict[tuple[str, str], tuple[str, dict]] = OrderedDict()
        self._max = max_entries

    def get(self, session_id: str, key: str):
        return self._done.get((session_id, key))

    def put(self, session_id: str, key: str, fingerprint: str, result: dict) -> None:
        self._done[(session_id, key)] = (fingerprint, result)
        while len(self._done) > self._max:
            self._done.popitem(last=False)


def _audit_default(record: dict) -> None:
    log.info("action_execution %s", record)


async def execute(
    proposal: k.ActionProposal, *, confirmed: Any, load_catalogue: Callable[[], Awaitable[k.CatalogueState]],
    perform: Callable[[k.ActionType, dict], Awaitable[dict]], ledger: ExecutionLedger,
    audit: Callable[[dict], None] = _audit_default,
) -> Execution:
    async with ledger.lock:  # serialises revalidate -> perform -> record so duplicates cannot interleave
        decision = k.validate(proposal, await load_catalogue(), k.IdempotencyLedger())  # loaded under the lock = current
        executed, replayed, reason, result = False, False, decision.reason, None
        prior = None
        if decision.fingerprint is not None:
            prior = ledger.get(proposal.context.session_id, decision.idempotency_key)
        try:
            if confirmed is not True:
                reason = "not_confirmed"
            elif prior is not None:
                if prior[0] != decision.fingerprint:
                    reason = "idempotency_conflict"
                else:
                    executed, replayed, reason, result = True, True, "ok", prior[1]
            elif decision.outcome != "validated":
                pass
            elif k.ActionType(decision.action_type) not in EXECUTABLE:
                reason = "unsupported_action"
            else:
                try:
                    result = await perform(k.ActionType(decision.action_type), proposal.params)
                    ledger.put(proposal.context.session_id, decision.idempotency_key, decision.fingerprint, result)
                    executed, reason = True, "ok"
                except Exception:  # fixed code only; never the exception text
                    reason = "execution_failed"
        finally:
            ref = result.get("reference") if isinstance(result, dict) else None
            audit({**decision.audit(), "outcome": "executed" if executed else "rejected", "reason": reason,
                   "executed": executed and not replayed, "replayed": replayed, "enquiry_reference": ref})
    return Execution("executed" if executed else "rejected", reason, replayed, result if executed else None, decision.action_type)
