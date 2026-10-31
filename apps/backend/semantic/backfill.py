"""Bounded, idempotent embedding backfill. Library only: nothing schedules it and no request path calls it.

One run = recover expired leases, purge embeddings of non-public products, queue one page of stale products,
then drain at most `limit` jobs. Re-running does no provider work for products whose hash is already current.
The caller supplies the provider (only the test-only fake exists; see semantic.embeddings).
"""
import asyncio
import uuid
from collections import Counter
from datetime import datetime

from repositories import semantic_embeddings as repo
from semantic.embeddings import VectorError, validate_vector
from semantic.representation import REPRESENTATION_VERSION, RepresentationError, represent

MAX_BATCH = 200


async def _process(sessions, provider, target, worker_id, job_id, product_id, now) -> str:
    try:
        revision = fingerprint = vector = None
        async with sessions() as s, s.begin():
            source = await repo.source_for(s, product_id)
            stored = await repo.stored_hash(s, product_id, target) if source else None
        if source:
            revision, product = source
            represented = represent(product)
            fingerprint = represented["fingerprint"]
            if stored != fingerprint:
                vector = validate_vector(await asyncio.to_thread(getattr(provider, "embed_passage", provider.embed), represented["text"]),
                                         provider.config.dimensions)
        async with sessions() as s, s.begin():
            return await repo.finish_job(s, job_id, worker_id, target, product_id, revision=revision,
                                         fingerprint=fingerprint, vector=vector, now=now)
    except (RepresentationError, VectorError) as exc:   # deterministic: retrying cannot help
        error, retryable = f"{type(exc).__name__}: {exc}", False
    except Exception as exc:                            # provider/transport/database trouble: bounded retry
        error, retryable = f"{type(exc).__name__}: {exc}", True
    async with sessions() as s, s.begin():
        return await repo.fail_job(s, job_id, worker_id, error, retryable=retryable, now=now)


async def run_backfill(sessions, provider, *, worker_id: str, limit: int = 50, after: uuid.UUID | None = None,
                       now: datetime | None = None) -> dict:
    """``sessions`` is an async_sessionmaker. Returns counts plus ``next_after`` (resume cursor, None when done)."""
    limit = max(1, min(limit, MAX_BATCH))
    cfg = provider.config
    target = repo.Target(cfg.provider, cfg.model, REPRESENTATION_VERSION)
    stats: Counter = Counter()
    async with sessions() as s, s.begin():
        stats["recovered"] = await repo.recover_expired_leases(s, now)
        stats["purged"] = await repo.purge_inactive(s, limit)
        stats["queued"], next_after = await repo.enqueue_stale(s, target, after, limit, now)
    for _ in range(limit):
        async with sessions() as s, s.begin():
            claimed = await repo.claim_next(s, worker_id, target, now)
        if claimed is None:
            break
        stats[await _process(sessions, provider, target, worker_id, *claimed, now)] += 1
    return {**stats, "next_after": str(next_after) if next_after else None}
