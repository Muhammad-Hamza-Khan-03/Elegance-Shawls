"""Cross-worker idempotency claims and audit records for confirmed assistant actions (M3-S4). Callers own the transaction.

`claim` is one atomic INSERT ... ON CONFLICT on (session_hash, idempotency_key): the first caller owns the row; a concurrent
caller blocks on the unique index until the claim commits, then sees it. A row is reclaimable only when it is `failed` or its
lease has expired (the owner crashed or stalled); every reclaim bumps `attempt`, and `commit`/`fail` apply only to the attempt
that still owns the row, so a stalled worker can never overwrite a newer outcome. The effect (the enquiry) and `commit` belong
in ONE transaction: a crash then leaves either both or neither, which is what makes a reclaim safe.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, null, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.relational_model import ActionExecution as A

LEASE_SECONDS = 30  # one DB transaction; comfortably above its worst case, short enough that a crash is retryable soon


@dataclass(frozen=True)
class Claim:
    state: str  # claimed | replay | conflict | in_progress | absent
    result: dict | None = None
    id: uuid.UUID | None = None
    attempt: int = 0


async def claim(session: AsyncSession, *, session_hash: str, key: str, action_type: str, fingerprint: str, audit: dict,
                create: bool, now: datetime, lease_seconds: int = LEASE_SECONDS) -> Claim:
    """`create=False` only looks: it never writes a claim (used when the request cannot be executed, so only a prior result counts)."""
    if create:
        values = dict(action_type=action_type, fingerprint=fingerprint, status="pending", lease_expires_at=now + timedelta(seconds=lease_seconds),
                      audit=audit, updated_at=now)
        owned = (await session.execute(
            pg_insert(A).values(session_hash=session_hash, idempotency_key=key, created_at=now, **values)
            .on_conflict_do_update(
                index_elements=[A.session_hash, A.idempotency_key],
                set_={**values, "attempt": A.attempt + 1, "result": null(), "reason": null()},
                where=or_(A.status == "failed", and_(A.status == "pending", A.lease_expires_at <= now)))
            .returning(A.id, A.attempt))).first()
        if owned:
            return Claim("claimed", id=owned.id, attempt=owned.attempt)
    prior = (await session.execute(select(A).where(A.session_hash == session_hash, A.idempotency_key == key))).scalar_one_or_none()
    if prior is None:
        return Claim("absent")
    if prior.status == "committed":
        if prior.fingerprint != fingerprint:
            return Claim("conflict")
        await session.execute(update(A).where(A.id == prior.id).values(replay_count=A.replay_count + 1))
        return Claim("replay", result=prior.result)
    if prior.status == "pending" and prior.fingerprint != fingerprint:
        return Claim("conflict")
    live = prior.status == "pending" and prior.lease_expires_at > now
    return Claim("in_progress") if create or live else Claim("absent")  # create: lost a race to a newer claim, retry shortly


async def _finish(session: AsyncSession, claim_: Claim, now: datetime, **values) -> bool:
    return (await session.execute(
        update(A).where(A.id == claim_.id, A.attempt == claim_.attempt, A.status == "pending")
        .values(updated_at=now, **values).returning(A.id))).first() is not None


async def mark_committed(session: AsyncSession, claim_: Claim, result: dict, now: datetime) -> bool:
    ref = result.get("reference") if isinstance(result, dict) else None
    final = {"outcome": "executed", "reason": "ok", "executed": True, "enquiry_reference": ref}
    return await _finish(session, claim_, now, status="committed", result=result, audit=A.audit.concat(final))


async def mark_failed(session: AsyncSession, claim_: Claim, reason: str, now: datetime) -> bool:
    final = {"outcome": "rejected", "reason": reason, "executed": False, "enquiry_reference": None}
    return await _finish(session, claim_, now, status="failed", reason=reason, audit=A.audit.concat(final))
