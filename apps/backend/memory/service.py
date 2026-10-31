"""Explicit customer memory (M4-S1): consent, create, list, correct, delete, retention. No model calls, no inference.

Rules, all fail-closed:
* memory is off until the customer opts in; every read and write of items needs current consent (only delete and delete-all
  work without it, so a customer can always erase);
* the acting customer comes from the authenticated principal only, and every query is scoped to it; another customer's item is
  indistinguishable from a missing one (`not_found`);
* create/update/delete are idempotent; a deleted or expired memory is never resurrected by a replayed create (`gone`);
* each state change writes a content-free audit row in the SAME transaction (no audit, no change). The audit holds ids, the
  category and field names, never a key, value, reason or source_ref.
Callers (routes) own the transaction and commit once after the service returns.
"""
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from memory import policy
from models.relational_model import MemoryItem
from repositories import admin as audit
from repositories import memory as repo


class MemoryRejected(Exception):
    """A refusal with a fixed, client-safe reason code."""

    STATUS = {"consent_required": 403, "not_found": 404, "idempotency_conflict": 409, "duplicate_key": 409, "limit_reached": 409, "gone": 410}

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason, self.status = reason, self.STATUS[reason]


async def _audit(session: AsyncSession, customer_id: uuid.UUID, action: str, target: str, **detail) -> None:
    await audit.add_audit(session, actor_type="customer", actor_id=str(customer_id), action=f"memory.{action}", target=target,
                          outcome="success", detail={"policy_version": policy.MEMORY_POLICY_VERSION, **detail})


async def _consented(session: AsyncSession, customer_id: uuid.UUID, *, lock: bool) -> None:
    consent = await repo.get_consent(session, customer_id, lock=lock)
    if consent is None or not consent.granted:
        raise MemoryRejected("consent_required")


# ---- consent ----------------------------------------------------------------------------------
async def get_consent(session: AsyncSession, customer_id: uuid.UUID) -> dict:
    consent = await repo.get_consent(session, customer_id)
    return {"granted": bool(consent and consent.granted), "policy_version": consent.policy_version if consent else policy.MEMORY_POLICY_VERSION,
            "changed_at": consent.changed_at if consent else None}


async def set_consent(session: AsyncSession, customer_id: uuid.UUID, granted: bool, now: datetime) -> dict:
    """Revoking hides stored memories (every item operation then needs consent) and keeps them until they expire or are deleted."""
    if await repo.set_consent(session, customer_id, granted, policy.MEMORY_POLICY_VERSION, now):
        await _audit(session, customer_id, "consent.grant" if granted else "consent.revoke", f"customer:{customer_id}")
    return await get_consent(session, customer_id)


# ---- items ------------------------------------------------------------------------------------
async def create(session: AsyncSession, customer_id: uuid.UUID, req, now: datetime) -> tuple[MemoryItem, bool]:
    """(item, replayed)."""
    await _consented(session, customer_id, lock=True)
    await repo.scrub_expired(session, now, customer_id)
    fp = repo.fingerprint(category=req.category, key=req.key, value=req.value, source=req.source, source_ref=req.source_ref,
                          reason=req.reason, retention_days=req.retention_days)
    prior = await repo.by_idempotency_key(session, customer_id, req.idempotency_key)
    if prior is not None:
        if prior.status != "active":
            raise MemoryRejected("gone")           # deleted or expired: a replay must not bring it back
        if prior.fingerprint != fp:
            raise MemoryRejected("idempotency_conflict")
        return prior, True
    if await repo.count_live(session, customer_id, now) >= policy.MAX_ACTIVE_ITEMS:
        raise MemoryRejected("limit_reached")
    if await repo.live_key_exists(session, customer_id, req.key):
        raise MemoryRejected("duplicate_key")      # change it with update, or delete it first
    item = await repo.insert_item(session, customer_id, req.idempotency_key, fp, now, category=req.category, key=req.key, value=req.value,
                                  source=req.source, source_ref=req.source_ref, reason=req.reason, retention_days=req.retention_days)
    await _audit(session, customer_id, "create", f"memory:{item.id}", category=item.category, source=item.source)
    return item, False


async def list_items(session: AsyncSession, customer_id: uuid.UUID, now: datetime) -> list[MemoryItem]:
    await _consented(session, customer_id, lock=False)
    return await repo.list_live(session, customer_id, now)


async def get_item(session: AsyncSession, customer_id: uuid.UUID, item_id: uuid.UUID, now: datetime) -> MemoryItem:
    await _consented(session, customer_id, lock=False)
    item = await repo.get_live(session, customer_id, item_id, now)
    if item is None:
        raise MemoryRejected("not_found")
    return item


async def update(session: AsyncSession, customer_id: uuid.UUID, item_id: uuid.UUID, req, now: datetime) -> MemoryItem:
    await _consented(session, customer_id, lock=True)
    item = await repo.get_live(session, customer_id, item_id, now, lock=True)
    if item is None:
        raise MemoryRejected("not_found")
    changes = {name: getattr(req, name) for name in ("value", "reason") if getattr(req, name) is not None}
    updated, changed = await repo.update_item(session, item, now, **changes)
    if changed:
        await _audit(session, customer_id, "update", f"memory:{item_id}", category=updated.category, fields=sorted(changes))
    return updated


async def delete(session: AsyncSession, customer_id: uuid.UUID, item_id: uuid.UUID, now: datetime) -> bool:
    """Idempotent and consent-free. True only when something was actually deleted; a repeat, or someone else's id, is a silent no-op."""
    category = await repo.scrub_item(session, customer_id, item_id, now)
    if category is not None:
        await _audit(session, customer_id, "delete", f"memory:{item_id}", category=category)
    return category is not None


async def delete_all(session: AsyncSession, customer_id: uuid.UUID, now: datetime) -> int:
    count = await repo.scrub_all(session, customer_id, now)
    if count:
        await _audit(session, customer_id, "delete_all", f"customer:{customer_id}", count=count)
    return count


async def purge_expired(session: AsyncSession, now: datetime) -> tuple[int, int]:
    """Retention job entry point (not scheduled here). One aggregate system audit row, no customer ids."""
    expired, removed = await repo.purge(session, now, policy.TOMBSTONE_DAYS)
    if expired or removed:
        await audit.add_audit(session, actor_type="system", actor_id="memory-retention", action="memory.purge", target=None, outcome="success",
                              detail={"expired": expired, "tombstones_removed": removed})
    return expired, removed
