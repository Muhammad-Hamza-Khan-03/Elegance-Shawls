"""arq job for embeddings, on its own queue. All state lives on the embedding row (lease, attempts, backoff, terminal state).

The job never raises except arq.Retry for a retryable provider failure that still has attempts left, so arq cannot
add retries beyond the row's max_attempts. A provider or Redis outage only delays vectors; it never touches the catalogue.
"""
import logging
import uuid

from arq import Retry

from configuration.config import settings
from search import embedding_service
from search.providers import NonRetryableEmbeddingError, provider_for
from workers.jobs import traced
from workers.queues import QueueUnavailable, enqueue

logger = logging.getLogger("elegance.worker")


async def enqueue_embedding(kind: str, row_id: uuid.UUID) -> str | None:
    """Deterministic job id per row, so a repeated enqueue is a no-op. None when Redis is down: the row stays queued."""
    try:
        return await enqueue("run_embedding_job", kind, str(row_id), queue="embeddings", _job_id=f"embed:{kind}:{row_id}")
    except QueueUnavailable:
        logger.warning("embedding enqueue skipped: queue unavailable")
        return None


@traced
async def run_embedding_job(ctx: dict, kind: str, row_id: str) -> dict:
    sessions = ctx.get("pg_sessions")
    if sessions is None:
        return {"skipped": "postgres is not configured"}
    if not settings.embedding_enabled:
        return {"skipped": "embeddings are disabled"}
    try:
        provider = ctx.get("embedding_provider") or provider_for(settings.embedding_provider, settings.embedding_dimensions)
    except NonRetryableEmbeddingError as exc:
        return {"skipped": str(exc)}
    try:
        result = await embedding_service.process(sessions, provider, kind, uuid.UUID(row_id),
                                                 lease_seconds=settings.embedding_lease_seconds,
                                                 backoff_seconds=settings.embedding_backoff_seconds)
    except Exception as exc:  # a bug must not cause an arq redelivery; the lease expires and a rerun resumes the row
        logger.error("embedding job crashed: %s", type(exc).__name__)
        return {"status": "error", "error": type(exc).__name__}
    if result["status"] == "retry":
        raise Retry(defer=result["delay"])
    return result
