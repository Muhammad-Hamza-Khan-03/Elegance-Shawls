"""Customer memory persistence (M4-S1). Callers own the transaction; nothing here commits.

Authorization lives in the predicate: every item query carries `customer_id`, so another customer's id (or one that does not
exist) is simply not found. Callers hold the consent row lock (`lock_consent`) while they mutate, which serialises one customer's
writes (exact item cap, consent flips cannot interleave with a write) without touching anyone else's.
"""
import hashlib
import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.relational_model import MemoryConsent as C, MemoryItem as M

_CONTENT_SCRUBBED = dict(status="deleted", key=None, value=None, reason=None, source_ref=None, fingerprint=None)


def fingerprint(*, category: str, key: str, value: str, source: str, source_ref: str | None, reason: str | None, retention_days: int) -> str:
    canonical = json.dumps([category, key, value, source, source_ref, reason, retention_days], ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---- consent ----------------------------------------------------------------------------------
async def get_consent(session: AsyncSession, customer_id: uuid.UUID, *, lock: bool = False) -> C | None:
    stmt = select(C).where(C.customer_id == customer_id)
    return (await session.execute(stmt.with_for_update() if lock else stmt)).scalar_one_or_none()


async def set_consent(session: AsyncSession, customer_id: uuid.UUID, granted: bool, policy_version: str, now: datetime) -> bool:
    """True when the state changed (a first decision counts); an identical repeat is a no-op."""
    values = dict(granted=granted, policy_version=policy_version, changed_at=now)
    stmt = pg_insert(C).values(customer_id=customer_id, **values).on_conflict_do_update(
        index_elements=[C.customer_id], set_=values, where=C.granted.is_distinct_from(granted)).returning(C.customer_id)
    return (await session.execute(stmt)).first() is not None


# ---- items ------------------------------------------------------------------------------------
def _live(customer_id: uuid.UUID, now: datetime):
    return (M.customer_id == customer_id, M.status == "active", M.expires_at > now)


async def count_live(session: AsyncSession, customer_id: uuid.UUID, now: datetime) -> int:
    return (await session.execute(select(func.count()).select_from(M).where(*_live(customer_id, now)))).scalar_one()


async def live_key_exists(session: AsyncSession, customer_id: uuid.UUID, key: str) -> bool:
    # Callers scrub expired rows first (scrub_expired), because an expired-but-unpurged row would still hold the unique key.
    return (await session.execute(select(M.id).where(M.customer_id == customer_id, M.status == "active", M.key == key))).first() is not None


async def by_idempotency_key(session: AsyncSession, customer_id: uuid.UUID, idempotency_key: str) -> M | None:
    return (await session.execute(select(M).where(M.customer_id == customer_id, M.idempotency_key == idempotency_key))).scalar_one_or_none()


async def insert_item(session: AsyncSession, customer_id: uuid.UUID, idempotency_key: str, fp: str, now: datetime, **fields) -> M | None:
    """None when this (customer, idempotency key) already exists."""
    expires = now + timedelta(days=fields["retention_days"])
    stmt = pg_insert(M).values(customer_id=customer_id, idempotency_key=idempotency_key, fingerprint=fp, created_at=now, updated_at=now,
                               expires_at=expires, **fields).on_conflict_do_nothing(index_elements=[M.customer_id, M.idempotency_key]).returning(M)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_live(session: AsyncSession, customer_id: uuid.UUID, item_id: uuid.UUID, now: datetime, *, lock: bool = False) -> M | None:
    stmt = select(M).where(M.id == item_id, *_live(customer_id, now))
    return (await session.execute(stmt.with_for_update() if lock else stmt)).scalar_one_or_none()


async def list_live(session: AsyncSession, customer_id: uuid.UUID, now: datetime) -> list[M]:
    return list((await session.execute(select(M).where(*_live(customer_id, now)).order_by(M.created_at.desc(), M.id.desc()))).scalars())


async def update_item(session: AsyncSession, item: M, now: datetime, **fields) -> tuple[M, bool]:
    """Applies only real changes: an identical repeat leaves version, expiry and updated_at alone (idempotent). A real change
    restarts the retention window, since the customer just re-affirmed the memory."""
    if all(getattr(item, name) == value for name, value in fields.items()):
        return item, False
    stmt = (update(M).where(M.id == item.id, M.customer_id == item.customer_id, M.status == "active")
            .values(**fields, version=M.version + 1, updated_at=now, expires_at=now + timedelta(days=item.retention_days)).returning(M))
    return (await session.execute(stmt)).scalar_one(), True


async def scrub_item(session: AsyncSession, customer_id: uuid.UUID, item_id: uuid.UUID, now: datetime) -> str | None:
    """Category of the item that was deleted, or None when there was nothing live to delete (already gone, or not this customer's)."""
    stmt = (update(M).where(M.id == item_id, M.customer_id == customer_id, M.status == "active")
            .values(**_CONTENT_SCRUBBED, deleted_at=now, updated_at=now).returning(M.category))
    return (await session.execute(stmt)).scalar_one_or_none()


async def scrub_all(session: AsyncSession, customer_id: uuid.UUID, now: datetime) -> int:
    stmt = update(M).where(M.customer_id == customer_id, M.status == "active").values(**_CONTENT_SCRUBBED, deleted_at=now, updated_at=now).returning(M.id)
    return len((await session.execute(stmt)).all())


async def scrub_expired(session: AsyncSession, now: datetime, customer_id: uuid.UUID | None = None) -> int:
    """Retention enforcer: expired content is scrubbed (all customers, or one when `customer_id` is given)."""
    stmt = update(M).where(M.status == "active", M.expires_at <= now)
    if customer_id is not None:
        stmt = stmt.where(M.customer_id == customer_id)
    return len((await session.execute(stmt.values(**_CONTENT_SCRUBBED, deleted_at=now, updated_at=now).returning(M.id))).all())


async def purge(session: AsyncSession, now: datetime, tombstone_days: int) -> tuple[int, int]:
    """(expired items scrubbed, old tombstones removed)."""
    expired = await scrub_expired(session, now)
    removed = await session.execute(delete(M).where(M.status == "deleted", M.deleted_at < now - timedelta(days=tombstone_days)).returning(M.id))
    return expired, len(removed.all())
