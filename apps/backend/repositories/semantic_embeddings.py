"""Embedding persistence (pgvector) and the backfill queue, on PostgreSQL. Callers own the transaction.

Freshness: an embedding is fresh when its content_hash equals the current fingerprint of the product's public
text (semantic.representation). product_revision records the revision it was read at; every catalogue mutation
bumps that revision, so `servable` uses revision equality as the cheap SQL-side filter and the backfill
re-checks the exact hash. Jobs use the same lease/retry/cancel contract as repositories/jobs.py. Only active
(publicly visible) products are ever embedded; embeddings of anything else are purged.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.relational_model import SemanticEmbeddingJob, Product, SemanticEmbedding
from semantic.representation import RepresentationError, represent

CLAIMABLE = ("queued", "retrying")
FINISHED = ("failed", "cancelled", "succeeded")
LEASE_SECONDS = 120
BACKOFF_SECONDS = 30
MAX_ATTEMPTS = 3
MAX_ERROR_LENGTH = 500


@dataclass(frozen=True)
class Target:
    provider: str
    model: str
    representation_version: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=BACKOFF_SECONDS * (2 ** max(attempts - 1, 0)))


def _vector_literal(vector) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def _product_dict(p: Product) -> dict:
    return {"name": p.name, "category": p.category, "material": p.material, "sizing": p.sizing,
            "main_description": p.main_description,
            "variants": [{"name": v.name, "color": v.color, "size": v.size, "description": v.description}
                         for v in p.variants if v.is_active]}


def _on(target: Target, model):
    return and_(model.provider == target.provider, model.model == target.model,
                model.representation_version == target.representation_version)


async def source_for(session: AsyncSession, product_id: uuid.UUID) -> tuple[int, dict] | None:
    """(revision, public product fields) or None when the product is missing or not publicly visible."""
    p = (await session.execute(select(Product).where(Product.id == product_id, Product.status == "active")
                               .execution_options(populate_existing=True))).scalar_one_or_none()
    return (p.revision, _product_dict(p)) if p else None


async def stored_hash(session: AsyncSession, product_id: uuid.UUID, target: Target) -> str | None:
    return (await session.execute(select(SemanticEmbedding.content_hash).where(
        SemanticEmbedding.product_id == product_id, _on(target, SemanticEmbedding)))).scalar_one_or_none()


async def enqueue_stale(session: AsyncSession, target: Target, after: uuid.UUID | None, limit: int,
                        now: datetime | None = None) -> tuple[int, uuid.UUID | None]:
    """Queue jobs for one bounded page of active products (id order, resume with the returned cursor).

    Idempotent: one job row per target; a live (queued/running/retrying) job is left alone, a finished one is
    reset. Returns (jobs queued, next cursor or None when the catalogue is exhausted).
    """
    ts = now or _now()
    stmt = (select(Product, SemanticEmbedding.content_hash, SemanticEmbedding.product_revision)
            .outerjoin(SemanticEmbedding, and_(SemanticEmbedding.product_id == Product.id, _on(target, SemanticEmbedding)))
            .where(Product.status == "active").order_by(Product.id).limit(limit)
            .execution_options(populate_existing=True))
    if after is not None:
        stmt = stmt.where(Product.id > after)
    rows = (await session.execute(stmt)).all()
    queued = 0
    for product, stored, stored_revision in rows:
        try:
            current = represent(_product_dict(product))["fingerprint"]
        except RepresentationError:
            continue  # unrepresentable text can never be embedded; skip rather than loop on it
        if stored == current and stored_revision == product.revision:
            continue
        job_id = (await session.execute(
            pg_insert(SemanticEmbeddingJob).values(
                product_id=product.id, provider=target.provider, model=target.model,
                representation_version=target.representation_version, status="queued", attempts=0,
                max_attempts=MAX_ATTEMPTS, available_at=ts, created_at=ts, updated_at=ts)
            .on_conflict_do_update(
                index_elements=["product_id", "provider", "model", "representation_version"],
                set_=dict(status="queued", attempts=0, available_at=ts, lease_owner=None, lease_expires_at=None,
                          cancel_requested=False, last_error=None, result=None, finished_at=None, updated_at=ts),
                where=SemanticEmbeddingJob.status.in_(FINISHED))
            .returning(SemanticEmbeddingJob.id))).scalar_one_or_none()
        queued += job_id is not None
    return queued, (rows[-1][0].id if len(rows) == limit else None)


async def purge_inactive(session: AsyncSession, limit: int) -> int:
    """Delete (bounded) embeddings of products that are no longer publicly visible: archive exclusion."""
    return (await session.execute(text(
        "DELETE FROM semantic_embeddings WHERE id IN (SELECT e.id FROM semantic_embeddings e "
        "JOIN products p ON p.id = e.product_id WHERE p.status <> 'active' LIMIT :n)"), {"n": limit})).rowcount


async def servable_product_ids(session: AsyncSession, target: Target, limit: int) -> list[uuid.UUID]:
    """Products whose embedding matches the current public representation and target."""
    if limit <= 0:
        return []
    stmt = (select(SemanticEmbedding.product_id, SemanticEmbedding.content_hash, Product)
            .join(Product, Product.id == SemanticEmbedding.product_id)
            .where(Product.status == "active", _on(target, SemanticEmbedding),
                   SemanticEmbedding.product_revision == Product.revision)
            .order_by(SemanticEmbedding.product_id))
    rows = (await session.execute(stmt)).all()
    servable = []
    for product_id, stored_hash, product in rows:
        try:
            current_hash = represent(_product_dict(product))["fingerprint"]
        except RepresentationError:
            continue
        if stored_hash == current_hash:
            servable.append(product_id)
            if len(servable) == limit:
                break
    return servable


async def claim_next(session: AsyncSession, worker_id: str, target: Target,
                     now: datetime | None = None) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Claim the next due job for this target -> (job id, product id)."""
    ts = now or _now()
    due = (select(SemanticEmbeddingJob.id)
           .where(SemanticEmbeddingJob.status.in_(CLAIMABLE), SemanticEmbeddingJob.available_at <= ts,
                  SemanticEmbeddingJob.cancel_requested.is_(False), _on(target, SemanticEmbeddingJob))
           .order_by(SemanticEmbeddingJob.available_at, SemanticEmbeddingJob.id).limit(1).with_for_update(skip_locked=True))
    row = (await session.execute(
        update(SemanticEmbeddingJob).where(SemanticEmbeddingJob.id == due.scalar_subquery())
        .values(status="running", lease_owner=worker_id, lease_expires_at=ts + timedelta(seconds=LEASE_SECONDS),
                updated_at=ts, attempts=SemanticEmbeddingJob.attempts + 1)
        .returning(SemanticEmbeddingJob.id, SemanticEmbeddingJob.product_id))).one_or_none()
    return (row[0], row[1]) if row else None


async def _owned(session: AsyncSession, job_id: uuid.UUID, worker_id: str) -> SemanticEmbeddingJob | None:
    return (await session.execute(
        select(SemanticEmbeddingJob).where(SemanticEmbeddingJob.id == job_id, SemanticEmbeddingJob.status == "running",
                                   SemanticEmbeddingJob.lease_owner == worker_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()


def _close(job: SemanticEmbeddingJob, status: str, ts: datetime, result: dict | None = None) -> str:
    job.status, job.result, job.lease_owner, job.lease_expires_at = status, result, None, None
    job.finished_at = job.updated_at = ts
    return status


async def finish_job(session: AsyncSession, job_id: uuid.UUID, worker_id: str, target: Target, product_id: uuid.UUID, *,
                     revision: int | None, fingerprint: str | None, vector, now: datetime | None = None) -> str:
    """Write the outcome under the lease. -> embedded | fresh | inactive | superseded | cancelled | lost.

    Nothing is written unless this worker still owns the lease, the job was not cancelled, the product is still
    active and its revision is still the one the text was read at (otherwise the next backfill redoes it).
    ``vector`` None with a fingerprint means the stored hash was already current (only the revision is refreshed).
    """
    ts = now or _now()
    job = await _owned(session, job_id, worker_id)
    if job is None:
        return "lost"
    if job.cancel_requested:
        return _close(job, "cancelled", ts)
    current = (await session.execute(select(Product.status, Product.revision).where(Product.id == product_id)
                                     .with_for_update(read=True))).one_or_none()
    if current is None or current.status != "active":
        await session.execute(text("DELETE FROM semantic_embeddings WHERE product_id = :p"), {"p": product_id})
        outcome = "inactive"
    elif revision is None or current.revision != revision:
        outcome = "superseded"
    elif vector is None:
        await session.execute(update(SemanticEmbedding).where(
            SemanticEmbedding.product_id == product_id, _on(target, SemanticEmbedding),
            SemanticEmbedding.content_hash == fingerprint).values(product_revision=revision, updated_at=ts))
        outcome = "fresh"
    else:
        await session.execute(text(
            "INSERT INTO semantic_embeddings (product_id, provider, model, dimensions, representation_version, "
            "content_hash, product_revision, embedding, updated_at) VALUES (:p, :provider, :model, :dims, :version, "
            ":hash, :rev, CAST(CAST(:vec AS text) AS vector), :ts) "
            "ON CONFLICT (product_id, provider, model, representation_version) DO UPDATE SET dimensions = :dims, "
            "content_hash = :hash, product_revision = :rev, embedding = EXCLUDED.embedding, updated_at = :ts"),
            {"p": product_id, "provider": target.provider, "model": target.model, "dims": len(vector),
             "version": target.representation_version, "hash": fingerprint, "rev": revision,
             "vec": _vector_literal(vector), "ts": ts})
        outcome = "embedded"
    _close(job, "succeeded", ts, {"outcome": outcome})
    await session.flush()
    return outcome


async def fail_job(session: AsyncSession, job_id: uuid.UUID, worker_id: str, error: str, *, retryable: bool,
                   now: datetime | None = None) -> str:
    """Retry with exponential backoff while attempts remain, else fail. -> retrying | failed | cancelled | lost."""
    ts = now or _now()
    job = await _owned(session, job_id, worker_id)
    if job is None:
        return "lost"
    if job.cancel_requested:
        status = _close(job, "cancelled", ts)
    else:
        job.last_error = error[:MAX_ERROR_LENGTH]
        if retryable and job.attempts < job.max_attempts:
            job.status, job.available_at, job.lease_owner, job.lease_expires_at = (
                "retrying", ts + _backoff(job.attempts), None, None)
            job.updated_at = ts
            status = "retrying"
        else:
            status = _close(job, "failed", ts)
    await session.flush()
    return status


async def recover_expired_leases(session: AsyncSession, now: datetime | None = None) -> int:
    """Return jobs of stopped workers to the queue (or fail them when out of attempts / cancel them)."""
    ts = now or _now()
    expired = (await session.execute(
        select(SemanticEmbeddingJob).where(SemanticEmbeddingJob.status == "running", SemanticEmbeddingJob.lease_expires_at < ts)
        .with_for_update(skip_locked=True).execution_options(populate_existing=True))).scalars().all()
    for job in expired:
        if job.cancel_requested:
            _close(job, "cancelled", ts)
        elif job.attempts >= job.max_attempts:
            _close(job, "failed", ts)
            job.last_error = "Lease expired after final attempt"
        else:
            job.status, job.available_at, job.lease_owner, job.lease_expires_at = (
                "retrying", ts + _backoff(job.attempts), None, None)
            job.last_error, job.updated_at = "Lease expired; worker presumed stopped", ts
    await session.flush()
    return len(expired)


async def cancel_pending(session: AsyncSession, now: datetime | None = None) -> int:
    """Cancel queued/retrying jobs now; running ones stop at their next write (finish_job honours the flag)."""
    ts = now or _now()
    queued = await session.execute(
        update(SemanticEmbeddingJob).where(SemanticEmbeddingJob.status.in_(CLAIMABLE))
        .values(status="cancelled", cancel_requested=True, finished_at=ts, updated_at=ts))
    running = await session.execute(
        update(SemanticEmbeddingJob).where(SemanticEmbeddingJob.status == "running").values(cancel_requested=True, updated_at=ts))
    return queued.rowcount + running.rowcount
