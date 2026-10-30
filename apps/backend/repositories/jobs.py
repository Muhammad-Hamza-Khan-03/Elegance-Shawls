"""Ingestion-job repository on PostgreSQL: leases, bounded retries with backoff, cancel and requeue.

Claiming uses SELECT ... FOR UPDATE SKIP LOCKED, so concurrent workers never own the same job, and
completion/failure are conditional on the caller still owning the lease, so a worker that lost its
lease cannot overwrite a newer outcome. Callers own the transaction (claim, then COMMIT to release the
row lock, run the job, then complete in a new transaction).
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from models.relational_model import IngestionJob

CLAIMABLE = ("queued", "retrying")
FINISHED = ("failed", "cancelled", "succeeded")
MAX_ERROR_LENGTH = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def idempotency_key_for(source_id: str, path: str) -> str:
    return hashlib.sha256(f"{source_id}\n{path}".encode()).hexdigest()


def _clip(message: str) -> str:
    return message[:MAX_ERROR_LENGTH]


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=settings.ingestion_job_backoff_seconds * (2 ** max(attempts - 1, 0)))


async def reload(session: AsyncSession, job_id: uuid.UUID) -> IngestionJob | None:
    return await session.get(IngestionJob, job_id, populate_existing=True)


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> IngestionJob | None:
    return await session.get(IngestionJob, job_id)


async def list_jobs(session: AsyncSession, limit: int) -> list[IngestionJob]:
    stmt = select(IngestionJob).order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())


async def create_job(session: AsyncSession, *, source_id: str, path: str, idempotency_key: str | None = None,
                     max_attempts: int | None = None, now: datetime | None = None) -> tuple[IngestionJob, bool]:
    """Create a job, or return the existing one for this idempotency key. -> (job, created)."""
    ts = now or _now()
    key = idempotency_key or idempotency_key_for(source_id, path)
    created_id = (await session.execute(
        pg_insert(IngestionJob).values(
            source_id=source_id, path=path, idempotency_key=key, status="queued", attempts=0,
            max_attempts=max_attempts or settings.ingestion_job_max_attempts, available_at=ts,
            created_at=ts, updated_at=ts)
        .on_conflict_do_nothing(index_elements=["idempotency_key"]).returning(IngestionJob.id))).scalar_one_or_none()
    if created_id is not None:
        return await reload(session, created_id), True
    existing = (await session.execute(select(IngestionJob).where(IngestionJob.idempotency_key == key))).scalar_one()
    return existing, False


async def requeue_job(session: AsyncSession, job_id: uuid.UUID, now: datetime | None = None) -> IngestionJob | None:
    """Explicit rerun of a finished job. Staging is idempotent, so reruns never duplicate."""
    ts = now or _now()
    found = (await session.execute(
        update(IngestionJob).where(IngestionJob.id == job_id, IngestionJob.status.in_(FINISHED))
        .values(status="queued", attempts=0, available_at=ts, lease_owner=None, lease_expires_at=None,
                cancel_requested=False, last_error=None, finished_at=None, updated_at=ts)
        .returning(IngestionJob.id))).scalar_one_or_none()
    return await reload(session, found) if found else None


async def claim_next(session: AsyncSession, worker_id: str, now: datetime | None = None,
                     only_ids: list[uuid.UUID] | None = None) -> IngestionJob | None:
    """Claim the next due job; ``only_ids`` limits a one-shot run to its own batch."""
    ts = now or _now()
    due = (select(IngestionJob.id)
           .where(IngestionJob.status.in_(CLAIMABLE), IngestionJob.available_at <= ts, IngestionJob.cancel_requested.is_(False))
           .order_by(IngestionJob.available_at, IngestionJob.id).limit(1).with_for_update(skip_locked=True))
    if only_ids is not None:
        due = due.where(IngestionJob.id.in_(list(only_ids)))
    claimed = (await session.execute(
        update(IngestionJob).where(IngestionJob.id == due.scalar_subquery())
        .values(status="running", lease_owner=worker_id,
                lease_expires_at=ts + timedelta(seconds=settings.ingestion_job_lease_seconds),
                heartbeat_at=ts, started_at=ts, updated_at=ts, attempts=IngestionJob.attempts + 1)
        .returning(IngestionJob.id))).scalar_one_or_none()
    return await reload(session, claimed) if claimed else None


async def heartbeat(session: AsyncSession, job_id: uuid.UUID, worker_id: str, now: datetime | None = None) -> bool:
    ts = now or _now()
    result = await session.execute(
        update(IngestionJob).where(IngestionJob.id == job_id, IngestionJob.status == "running",
                                   IngestionJob.lease_owner == worker_id)
        .values(heartbeat_at=ts, updated_at=ts,
                lease_expires_at=ts + timedelta(seconds=settings.ingestion_job_lease_seconds))
        .returning(IngestionJob.id))
    return result.scalar_one_or_none() is not None


async def _owned(session: AsyncSession, job_id: uuid.UUID, worker_id: str) -> IngestionJob | None:
    return (await session.execute(
        select(IngestionJob).where(IngestionJob.id == job_id, IngestionJob.status == "running",
                                   IngestionJob.lease_owner == worker_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()


def _cancel(job: IngestionJob, ts: datetime) -> None:
    job.status, job.lease_owner, job.lease_expires_at, job.finished_at, job.updated_at = "cancelled", None, None, ts, ts


async def complete_job(session: AsyncSession, job_id: uuid.UUID, worker_id: str, result: dict,
                       now: datetime | None = None) -> IngestionJob | None:
    ts = now or _now()
    job = await _owned(session, job_id, worker_id)
    if job is None:
        return None  # lease lost: someone else owns the outcome now
    if job.cancel_requested:
        _cancel(job, ts)
    else:
        job.status, job.result, job.last_error = "succeeded", result, None
        job.lease_owner = job.lease_expires_at = None
        job.finished_at = job.updated_at = ts
    await session.flush()
    return job


async def fail_job(session: AsyncSession, job_id: uuid.UUID, worker_id: str, error: str, *, retryable: bool,
                   now: datetime | None = None) -> IngestionJob | None:
    """Retry with exponential backoff while attempts remain; otherwise fail terminally."""
    ts = now or _now()
    job = await _owned(session, job_id, worker_id)
    if job is None:
        return None
    if job.cancel_requested:
        _cancel(job, ts)
    else:
        job.lease_owner = job.lease_expires_at = None
        job.last_error, job.last_error_retryable, job.updated_at = _clip(error), retryable, ts
        if retryable and job.attempts < job.max_attempts:
            job.status, job.available_at = "retrying", ts + _backoff(job.attempts)
        else:
            job.status, job.finished_at = "failed", ts
    await session.flush()
    return job


async def recover_expired_leases(session: AsyncSession, now: datetime | None = None) -> int:
    """Return jobs whose worker stopped heartbeating to the queue, or fail them when out of attempts."""
    ts = now or _now()
    expired = (await session.execute(
        select(IngestionJob).where(IngestionJob.status == "running", IngestionJob.lease_expires_at < ts)
        .with_for_update(skip_locked=True).execution_options(populate_existing=True))).scalars().all()
    for job in expired:
        if job.cancel_requested:
            job.status, job.finished_at = "cancelled", ts
        elif job.attempts >= job.max_attempts:
            job.status, job.finished_at, job.last_error = "failed", ts, "Lease expired after final attempt"
        else:
            job.status, job.available_at = "retrying", ts + _backoff(job.attempts)
            job.last_error = "Lease expired; worker presumed stopped"
        job.lease_owner = job.lease_expires_at = None
        job.updated_at = ts
    await session.flush()
    return len(expired)


async def cancel_job(session: AsyncSession, job_id: uuid.UUID, now: datetime | None = None) -> IngestionJob | None:
    """Queued/retrying jobs cancel immediately; running ones stop at the worker's next checkpoint."""
    ts = now or _now()
    job = (await session.execute(
        select(IngestionJob).where(IngestionJob.id == job_id).with_for_update()
        .execution_options(populate_existing=True))).scalar_one_or_none()
    if job is None:
        return None
    if job.status in CLAIMABLE:
        job.status, job.cancel_requested, job.finished_at, job.updated_at = "cancelled", True, ts, ts
    elif job.status == "running":
        job.cancel_requested, job.updated_at = True, ts
    else:
        return None
    await session.flush()
    return job
