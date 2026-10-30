"""Redis/arq queue names and enqueue helpers. All failures surface as QueueUnavailable."""
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job, JobStatus

from configuration.config import settings
from observability.tracing import current_traceparent

QUEUES = {
    "default": "elegance:ai:default",
    "embeddings": "elegance:ai:embeddings",
    "enrichment": "elegance:ai:enrichment",
    "memory": "elegance:ai:memory",
    "asr": "elegance:ai:asr",
}

_pool: ArqRedis | None = None


class QueueUnavailable(RuntimeError):
    pass


def redis_settings() -> RedisSettings:
    settings_ = RedisSettings.from_dsn(settings.redis_url or "redis://localhost:6379")
    settings_.conn_timeout = max(1, int(settings.redis_connect_timeout_seconds))
    settings_.conn_retries = 1
    return settings_


async def _get_pool() -> ArqRedis:
    global _pool
    if not settings.redis_url:
        raise QueueUnavailable("Redis is not configured")
    if _pool is None:
        try:
            _pool = await create_pool(redis_settings())
        except Exception as exc:
            raise QueueUnavailable("Redis is unavailable") from exc
    return _pool


async def close_queue_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
    _pool = None


async def enqueue(function: str, *args, queue: str = "default", **kwargs) -> str:
    # Every job runs under workers.jobs.traced, which pops this and continues the API request's trace.
    if (traceparent := current_traceparent()):
        kwargs["traceparent"] = traceparent
    try:
        job = await (await _get_pool()).enqueue_job(function, *args, _queue_name=QUEUES[queue], **kwargs)
    except QueueUnavailable:
        raise
    except Exception as exc:
        raise QueueUnavailable("Redis is unavailable") from exc
    if job is None:
        raise QueueUnavailable("Job was not enqueued")
    return job.job_id


async def job_state(job_id: str, queue: str = "default") -> dict:
    try:
        job = Job(job_id, await _get_pool(), _queue_name=QUEUES[queue])
        state = await job.status()
        if state is JobStatus.not_found:
            return {"status": state.value}
        info = await job.result_info() if state is JobStatus.complete else None
        return {"status": state.value, "success": info.success if info else None,
                "result": info.result if info and info.success else None}
    except QueueUnavailable:
        raise
    except Exception as exc:
        raise QueueUnavailable("Redis is unavailable") from exc


async def worker_is_alive(queue: str = "default") -> bool:
    """arq refreshes this key with a TTL while a worker on the queue is running."""
    try:
        return bool(await (await _get_pool()).exists(f"{QUEUES[queue]}:health-check"))
    except Exception:
        return False
