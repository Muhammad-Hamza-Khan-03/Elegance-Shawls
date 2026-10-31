"""PostgreSQL-backed execution store for the M3-S3 executor (M3-S4): durable, multi-worker idempotency and audit.

Owns the transaction boundaries the executor needs (the repository never commits):
  claim   - its own short transaction, committed immediately so other workers see `pending`;
  commit  - `perform` (the effect) and the committed mark in ONE transaction; any failure rolls both back;
  fail    - its own transaction, marks the claim retryable.
A worker that dies between claim and commit leaves a `pending` row and no effect; the lease expiry makes it reclaimable.
(shortcut: no reaper or retention job for old rows; they are tiny, add one with the events retention if volume warrants.)
"""
import hashlib
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from repositories import action_executions as repo
from repositories.action_executions import Claim


class LeaseLost(Exception):
    """Another worker reclaimed this execution after its lease expired; this attempt's effect has been rolled back."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SqlExecutionStore:
    def __init__(self, session: AsyncSession, now: Callable[[], datetime] = _now, lease_seconds: int = repo.LEASE_SECONDS):
        self.session, self._now, self._lease = session, now, lease_seconds

    async def claim(self, session_id: str, key: str, fingerprint: str, action_type: str, audit: dict, *, create: bool) -> Claim:
        try:
            out = await repo.claim(self.session, session_hash=hashlib.sha256(session_id.encode()).hexdigest(), key=key, action_type=action_type,
                                   fingerprint=fingerprint, audit=audit, create=create, now=self._now(), lease_seconds=self._lease)
            await self.session.commit()  # also ends the caller's earlier read transaction
            return out
        except Exception:
            await self.session.rollback()
            raise

    async def commit(self, claim: Claim, perform: Callable[[], Awaitable[dict]]) -> dict:
        try:
            result = await perform()
            if not await repo.mark_committed(self.session, claim, result, self._now()):
                raise LeaseLost
            await self.session.commit()
            return result
        except Exception:
            await self.session.rollback()
            raise

    async def fail(self, claim: Claim, reason: str) -> None:
        try:
            await repo.mark_failed(self.session, claim, reason, self._now())  # no-op if the attempt no longer owns the row
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
