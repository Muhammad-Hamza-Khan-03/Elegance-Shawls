"""Real Redis + a real in-process arq worker."""
import asyncio

import pytest
from arq.worker import Worker
from redis.asyncio import Redis

from configuration.config import settings
from security.rate_limit import RateLimitMiddleware
from tests.test_redis_queue_and_rate_limit import _ok, _sequence
from workers import queues
from workers.jobs import sample_job
from workers.queues import redis_settings


@pytest.fixture
def redis_settings_env(redis_url, monkeypatch):
    monkeypatch.setattr(settings, "redis_url", redis_url)
    asyncio.run(Redis.from_url(redis_url).flushdb())
    return redis_url


def _worker(**kwargs) -> Worker:
    return Worker(functions=[sample_job], redis_settings=redis_settings(), queue_name=queues.QUEUES["default"],
                  handle_signals=False, max_tries=3, **kwargs)


def _run_job(value, fail_times=0):
    async def go():
        queues._pool = None
        try:
            job_id = await queues.enqueue("sample_job", value, fail_times)
            worker = _worker(burst=True)
            await worker.async_run()
            await worker.close()
            return await queues.job_state(job_id)
        finally:
            await queues.close_queue_pool()

    return asyncio.run(go())


def test_sample_job_runs_in_worker_and_result_is_observable(redis_settings_env):
    state = _run_job("hello")
    assert state["status"] == "complete" and state["success"] is True
    assert state["result"] == {"echo": "hello", "attempt": 1}


def test_retries_are_bounded(redis_settings_env):
    assert _run_job("ok-after-retries", fail_times=2)["result"]["attempt"] == 3
    assert _run_job("never", fail_times=5)["success"] is False


def test_worker_heartbeat_is_visible_and_worker_stops_gracefully(redis_settings_env):
    async def go():
        queues._pool = None
        worker = _worker(health_check_interval=1)
        task = asyncio.create_task(worker.async_run())
        try:
            for _ in range(40):
                if await queues.worker_is_alive():
                    break
                await asyncio.sleep(0.25)
            alive = await queues.worker_is_alive()
        finally:
            await worker.close()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await queues.close_queue_pool()
        return alive

    assert asyncio.run(go()) is True


def test_rate_limit_is_shared_across_replicas_on_real_redis(redis_settings_env, monkeypatch):
    from database import redis_client
    monkeypatch.setattr(redis_client, "_client", None)
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 2)
    a, b = RateLimitMiddleware(_ok), RateLimitMiddleware(_ok)
    assert _sequence(a, b, a, b) == [200, 200, 429, 429]


def test_trace_context_flows_api_to_redis_to_worker(redis_settings_env):
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from observability import tracing

    exporter = InMemorySpanExporter()
    tracing.add_exporter(exporter)

    async def go():
        queues._pool = None
        try:
            with tracing.span("api.request") as api_span:
                await queues.enqueue("sample_job", "traced")
            worker = _worker(burst=True)
            await worker.async_run()
            await worker.close()
            return api_span.get_span_context()
        finally:
            await queues.close_queue_pool()

    api_ctx = asyncio.run(go())
    [job] = [s for s in exporter.get_finished_spans() if s.name == "worker.job"]
    assert job.context.trace_id == api_ctx.trace_id and job.parent.span_id == api_ctx.span_id


def test_llm_budget_is_shared_across_instances_on_real_redis(redis_settings_env):
    from llm.gateway import BudgetExceededError, BudgetTracker

    async def go():
        client = Redis.from_url(redis_settings_env)
        a, b = BudgetTracker(0.01, 10, 0.8, redis=client), BudgetTracker(0.01, 10, 0.8, redis=client)
        await a.record(0.006)
        await b.record(0.006)                   # B's own ledger says 0.006; the shared one says 0.012
        try:
            await a.check()
        except BudgetExceededError:
            return True
        finally:
            await client.aclose()
        return False

    assert asyncio.run(go()) is True
