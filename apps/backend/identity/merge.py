"""Conservative, explicit attribution of recent anonymous events to a local customer.

The caller resolves both principals: a live customer session and a signed anonymous event token. No browser id selects a row.
Only event ownership changes; memory, preferences and conversations remain untouched. One transaction contains the ledger,
event updates and content-free audit. A failed audit aborts the entire merge.
"""
import hashlib
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.relational_model import AnonymousMerge, Event
from repositories import admin as audit

MAX_AGE = timedelta(hours=24)
MAX_EVENTS = 100


class MergeRejected(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def validate_candidate(events: list[tuple[object, datetime]], now: datetime) -> None:
    if not events:
        raise MergeRejected("empty")
    if len(events) > MAX_EVENTS:
        raise MergeRejected("too_many_events")
    for owner, created_at in events:
        if owner is not None:
            raise MergeRejected("ownership_conflict")
        if created_at.tzinfo is None or created_at > now or now - created_at > MAX_AGE:
            raise MergeRejected("stale")


async def merge_anonymous_events(session: AsyncSession, customer_id: uuid.UUID, session_id: str, now: datetime) -> dict:
    """Merge all or none. A second caller cannot reassign a signed anonymous session to another customer."""
    session_hash = hashlib.sha256(session_id.encode()).hexdigest()
    # Serialise by anonymous session across workers, including a zero-event source. Hash collision only over-serialises.
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:sid, 0))"), {"sid": session_id})
    prior = (await session.execute(select(AnonymousMerge).where(AnonymousMerge.session_hash == session_hash))).scalar_one_or_none()
    if prior is not None:
        if prior.customer_id != customer_id:
            raise MergeRejected("ownership_conflict")
        if (await session.execute(select(Event.id).where(Event.session_id == session_id, Event.customer_id.is_distinct_from(customer_id))
                                  .limit(1))).first() is not None:
            raise MergeRejected("source_changed")
        return {"merged": prior.merged_count, "replayed": True}

    rows = (await session.execute(select(Event.id, Event.customer_id, Event.created_at)
                                  .where(Event.session_id == session_id).order_by(Event.id).limit(MAX_EVENTS + 1).with_for_update())).all()
    validate_candidate([(row.customer_id, row.created_at) for row in rows], now)
    await session.execute(update(Event).where(Event.id.in_([row.id for row in rows]), Event.customer_id.is_(None))
                          .values(customer_id=customer_id))
    session.add(AnonymousMerge(session_hash=session_hash, customer_id=customer_id, merged_count=len(rows)))
    await audit.add_audit(session, actor_type="customer", actor_id=str(customer_id), action="customer.merge_anonymous",
                          target=f"anonymous-session:{session_hash}", outcome="success", detail={"events": len(rows)})
    return {"merged": len(rows), "replayed": False}
