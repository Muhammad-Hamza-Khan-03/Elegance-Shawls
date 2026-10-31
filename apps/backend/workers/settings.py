"""Run with: arq workers.settings.WorkerSettings   (health: arq --check workers.settings.WorkerSettings)"""
import logging

from arq import cron

from configuration.config import settings
from database.pg import make_engine, postgres_configured
from sqlalchemy.ext.asyncio import async_sessionmaker
from observability.tracing import configure_exporters
from workers.jobs import purge_events_job, refresh_llm_models_job, sample_job
from workers.embedding_jobs import run_embedding_job
from workers.enrichment_jobs import run_enrichment_job
from workers.queues import QUEUES, redis_settings

logger = logging.getLogger("elegance.worker")


async def on_startup(ctx: dict) -> None:
    configure_exporters()
    if postgres_configured():
        ctx["pg_engine"] = make_engine()
        ctx["pg_sessions"] = async_sessionmaker(ctx["pg_engine"], expire_on_commit=False)
    logger.info("worker started queue=%s max_jobs=%s", settings.worker_queue, settings.worker_max_jobs)


async def on_shutdown(ctx: dict) -> None:
    if "pg_engine" in ctx:
        await ctx["pg_engine"].dispose()
    logger.info("worker stopped")


class WorkerSettings:
    functions = [sample_job, purge_events_job, refresh_llm_models_job, run_enrichment_job]   # run_embedding_job is registered below (its own queue)
    # Discovery is advisory and bounded; worker remains the only scheduler.
    cron_jobs = [cron(purge_events_job, hour=3, minute=17), cron(refresh_llm_models_job, hour=4, minute=17)]
    queue_name = settings.worker_queue
    redis_settings = redis_settings()
    # Bounded concurrency, runtime and retries so one bad job cannot starve the box.
    max_jobs = settings.worker_max_jobs
    job_timeout = settings.worker_job_timeout_seconds
    max_tries = settings.worker_max_tries
    keep_result = 3600
    health_check_interval = 30
    # On SIGTERM arq stops taking jobs and waits for running ones before exiting.
    job_completion_wait = 20
    on_startup = on_startup
    on_shutdown = on_shutdown


class EmbeddingWorkerSettings:
    """Run with: arq workers.settings.EmbeddingWorkerSettings. Own queue, no cron and nothing at startup: no backfill here."""
    functions = [run_embedding_job]
    queue_name = QUEUES["embeddings"]
    redis_settings = redis_settings()
    max_jobs = settings.embedding_max_jobs
    job_timeout = settings.embedding_job_timeout_seconds
    max_tries = settings.embedding_max_attempts + 1  # the row's own attempt counter is the real bound
    keep_result = 3600
    health_check_interval = 30
    job_completion_wait = 20
    on_startup = on_startup
    on_shutdown = on_shutdown
