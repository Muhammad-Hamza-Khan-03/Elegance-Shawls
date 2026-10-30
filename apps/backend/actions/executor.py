"""M3-S3/S4 execution adapters for add_to_cart and start_whatsapp_enquiry: runs only on an explicit user confirmation.

Every call re-runs the M3-S1 kernel against the *current* catalogue with a throwaway ledger (nothing cached from the model
turn is trusted), then performs the action through the injected `perform` callable. Executions are idempotent per
(session, key) across workers through the injected `store` (actions/store.py, PostgreSQL): a repeat with the same request
returns the stored result, a different request under the same key conflicts, a request still running elsewhere is
`execution_in_progress` (retry shortly), a failed or crashed attempt is retryable, and `perform` only ever runs for a caller
that holds the claim. Audit records are fixed-shape: hashed session ref, opaque ids, codes and the enquiry reference only;
never raw ids, params, prices or exception text. They are logged here and stored durably with the claim.

`store` contract: `claim(session_id, key, fingerprint, action_type, audit, *, create) -> Claim(state, result)` with state
claimed | replay | conflict | in_progress | absent; `commit(claim, perform) -> result` (effect and commit atomic);
`fail(claim, reason)`.
"""
import logging
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


def _audit_default(record: dict) -> None:
    log.info("action_execution %s", record)


async def execute(
    proposal: k.ActionProposal, *, confirmed: Any, load_catalogue: Callable[[], Awaitable[k.CatalogueState]],
    perform: Callable[[k.ActionType, dict], Awaitable[dict]], store: Any,
    audit: Callable[[dict], None] = _audit_default,
) -> Execution:
    decision = k.validate(proposal, await load_catalogue(), k.IdempotencyLedger())  # current state, nothing cached
    executed, replayed, reason, result = False, False, decision.reason, None
    try:
        if confirmed is not True:
            reason = "not_confirmed"
        elif decision.fingerprint is not None:
            action = k.ActionType(decision.action_type)
            runnable = decision.outcome == "validated" and action in EXECUTABLE
            claim = await store.claim(proposal.context.session_id, decision.idempotency_key, decision.fingerprint, action.value,
                                      decision.audit(), create=runnable)  # a prior result wins over a now-stale catalogue, as before
            if claim.state == "replay":
                executed, replayed, reason, result = True, True, "ok", claim.result
            elif claim.state == "conflict":
                reason = "idempotency_conflict"
            elif claim.state == "in_progress":
                reason = "execution_in_progress"
            elif claim.state == "absent":
                reason = decision.reason if decision.outcome != "validated" else "unsupported_action"
            else:
                try:
                    result = await store.commit(claim, lambda: perform(action, proposal.params))
                    executed, reason = True, "ok"
                except Exception:  # fixed code only; never the exception text
                    reason = "execution_failed"
                    try:
                        await store.fail(claim, reason)
                    except Exception:  # the lease expiry makes the claim retryable anyway
                        log.error("action_execution_failure_not_recorded")
    finally:
        ref = result.get("reference") if isinstance(result, dict) else None
        audit({**decision.audit(), "outcome": "executed" if executed else "rejected", "reason": reason,
               "executed": executed and not replayed, "replayed": replayed, "enquiry_reference": ref})
    return Execution("executed" if executed else "rejected", reason, replayed, result if executed else None, decision.action_type)
