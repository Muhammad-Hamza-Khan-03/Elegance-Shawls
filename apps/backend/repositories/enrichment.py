"""Enrichment suggestions: idempotent create and conditional state changes. Callers own the transaction (no commits).

Every state change is conditional on the current status, so a cancelled suggestion can never be overwritten by a
worker that was still running, and a finished one can never be re-claimed.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from enrichment.contract import MAX_ATTEMPTS
from models.relational_model import EnrichmentSuggestion as E

MAX_ERROR_LENGTH = 300


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get(session: AsyncSession, suggestion_id: uuid.UUID) -> E | None:
    return await session.get(E, suggestion_id, populate_existing=True)


async def latest_for(session: AsyncSession, staged_id: uuid.UUID) -> E | None:
    stmt = select(E).where(E.staged_product_id == staged_id).order_by(E.created_at.desc(), E.id.desc()).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def create(session: AsyncSession, *, staged_id: uuid.UUID, input_hash: str, prompt_version: str, model: str,
                 vocabulary_version: str, provider: str, trace_id: str | None) -> tuple[E, bool]:
    """Insert a queued suggestion, or return the existing one: same idempotency key, else the staged product's active one."""
    created_id = (await session.execute(
        pg_insert(E).values(staged_product_id=staged_id, input_content_hash=input_hash, prompt_version=prompt_version,
                            model=model, vocabulary_version=vocabulary_version, provider=provider, trace_id=trace_id)
        .on_conflict_do_nothing().returning(E.id))).scalar_one_or_none()  # either unique index may conflict
    if created_id is not None:
        return await get(session, created_id), True
    same_key = select(E).where(E.staged_product_id == staged_id, E.input_content_hash == input_hash,
                               E.prompt_version == prompt_version, E.model == model)
    existing = (await session.execute(same_key)).scalar_one_or_none()
    if existing is None:  # a different request is still active for this staged product
        existing = (await session.execute(select(E).where(E.staged_product_id == staged_id, E.status.in_(("queued", "running"))))).scalar_one()
    return existing, False


async def claim(session: AsyncSession, suggestion_id: uuid.UUID) -> E | None:
    """queued -> running with the first attempt counted; None when it was cancelled, finished or already claimed."""
    ts = _now()
    found = (await session.execute(
        update(E).where(E.id == suggestion_id, E.status == "queued")
        .values(status="running", attempts=1, started_at=ts, updated_at=ts).returning(E.id))).scalar_one_or_none()
    return await get(session, found) if found else None


async def begin_retry(session: AsyncSession, suggestion_id: uuid.UUID, error: str) -> bool:
    """Count one more attempt (max MAX_ATTEMPTS) while still running; False tells the worker to stop."""
    return (await session.execute(
        update(E).where(E.id == suggestion_id, E.status == "running", E.attempts < MAX_ATTEMPTS)
        .values(attempts=E.attempts + 1, last_error=error[:MAX_ERROR_LENGTH], updated_at=_now())
        .returning(E.id))).scalar_one_or_none() is not None


async def finish(session: AsyncSession, suggestion_id: uuid.UUID, *, status: str, suggestions: dict | None = None,
                 validation_errors: list[str] | None = None, last_error: str | None = None) -> E | None:
    """running (or queued, for a failed enqueue) -> succeeded/failed; None when it is no longer active."""
    ts = _now()
    found = (await session.execute(
        update(E).where(E.id == suggestion_id, E.status.in_(("queued", "running")))
        .values(status=status, suggestions=suggestions, validation_errors=validation_errors or [],
                last_error=last_error[:MAX_ERROR_LENGTH] if last_error else None, finished_at=ts, updated_at=ts)
        .returning(E.id))).scalar_one_or_none()
    return await get(session, found) if found else None


async def cancel(session: AsyncSession, staged_id: uuid.UUID, suggestion_id: uuid.UUID) -> E | None:
    ts = _now()
    found = (await session.execute(
        update(E).where(E.id == suggestion_id, E.staged_product_id == staged_id, E.status.in_(("queued", "running")))
        .values(status="cancelled", finished_at=ts, updated_at=ts).returning(E.id))).scalar_one_or_none()
    return await get(session, found) if found else None
