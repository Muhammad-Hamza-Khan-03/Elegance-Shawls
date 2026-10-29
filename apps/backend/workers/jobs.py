import logging

from functools import wraps

from arq import Retry

from observability.tracing import context_from_traceparent, span

logger = logging.getLogger("elegance.worker")


def traced(fn):
    """Wraps an arq job in a span carrying the job name and attempt (no arguments: they may hold PII).

    Restores the trace context the API put in the payload (`traceparent`), so API request and
    worker job share one trace. Cron jobs have no such kwarg and start a fresh trace.
    """
    @wraps(fn)
    async def wrapper(ctx, *args, traceparent=None, **kwargs):
        parent = context_from_traceparent(traceparent)
        with span("worker.job", parent=parent, job=fn.__name__, attempt=ctx.get("job_try", 1)):
            return await fn(ctx, *args, **kwargs)

    return wrapper


@traced
async def purge_events_job(ctx: dict) -> dict:
    """Retention for interaction events, run by the worker's cron (see WorkerSettings.cron_jobs)."""
    from events.retention import purge_expired_events

    sessions = ctx.get("pg_sessions")
    if sessions is None:
        return {"skipped": "postgres is not configured"}
    async with sessions() as session:
        return {"deleted": await purge_expired_events(session)}


@traced
async def sample_job(ctx: dict, value: str, fail_times: int = 0) -> dict:
    """Round-trips a value; fails `fail_times` times first to exercise bounded retries."""
    attempt = ctx["job_try"]
    if attempt <= fail_times:
        raise Retry(defer=0.2)
    return {"echo": value, "attempt": attempt}


@traced
async def refresh_llm_models_job(ctx: dict, provider: str | None = None) -> dict:
    """Bounded/idempotent scheduled advisory refresh; failures never affect the worker."""
    from llm.model_discovery import refresh_models
    return await refresh_models(provider)
