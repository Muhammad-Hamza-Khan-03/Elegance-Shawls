import asyncio

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import main
from configuration.config import settings
from llm.fake import FakeProvider
from llm.gateway import BudgetTracker, LLMGateway
from observability import langfuse_client, tracing
from workers import queues
from workers.jobs import sample_job

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"


class CapturingPool:
    def __init__(self):
        self.calls = []

    async def enqueue_job(self, function, *args, **kwargs):
        kwargs.pop("_queue_name", None)  # arq consumes this itself
        self.calls.append((function, args, kwargs))

        class Job:
            job_id = "job-1"

        return Job()


@pytest.fixture
def exporter():
    exp = InMemorySpanExporter()
    tracing.add_exporter(exp)
    return exp


@pytest.fixture
def pool(monkeypatch):
    fake = CapturingPool()

    async def get_pool():
        return fake

    monkeypatch.setattr(queues, "_get_pool", get_pool)
    return fake


def spans(exporter, name):
    return [s for s in exporter.get_finished_spans() if s.name == name]


def test_enqueue_carries_the_current_trace_and_worker_continues_it(exporter, pool):
    async def flow():
        with tracing.span("api.request") as api_span:
            await queues.enqueue("sample_job", "x")
        _, _, kwargs = pool.calls[0]
        await sample_job({"job_try": 1}, "x", **kwargs)
        return api_span.get_span_context()

    api_ctx = asyncio.run(flow())
    [worker] = spans(exporter, "worker.job")
    assert worker.context.trace_id == api_ctx.trace_id               # one trace
    assert worker.parent.span_id == api_ctx.span_id                  # child of the enqueuing span


def test_http_request_trace_reaches_the_job_payload(exporter, pool, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "k")
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1000)
    monkeypatch.setattr(settings, "admin_rate_limit_per_minute", 1000)
    response = TestClient(main.create_app()).post(
        "/v1/admin/jobs/sample", json={"value": "v"}, headers={"X-Admin-Key": "k", "traceparent": TRACEPARENT})
    assert response.status_code == 202 and response.headers["x-trace-id"] == TRACE_ID
    carried = pool.calls[0][2]["traceparent"]
    assert carried.split("-")[1] == TRACE_ID and carried.split("-")[2] != "00f067aa0ba902b7"


def test_job_without_a_traceparent_starts_its_own_trace(exporter):
    asyncio.run(sample_job({"job_try": 1}, "cron-like"))
    assert spans(exporter, "worker.job")[-1].parent is None


def test_enqueue_outside_a_span_adds_no_traceparent(pool):
    asyncio.run(queues.enqueue("sample_job", "x"))
    assert "traceparent" not in pool.calls[0][2]


def test_payload_never_contains_job_arguments_in_the_span(exporter):
    asyncio.run(sample_job({"job_try": 1}, "customer@example.com"))
    assert "customer@example.com" not in str([dict(s.attributes) for s in exporter.get_finished_spans()])


# --- optional Langfuse ------------------------------------------------------------------------
class FakeLangfuse:
    def __init__(self):
        self.calls = []

    def start_observation(self, **kwargs):
        self.calls.append(kwargs)

        class Obs:
            def end(self_inner):
                self.ended = True

        return Obs()


MESSAGES = [{"role": "user", "content": "private customer text"}]


def gateway():
    return LLMGateway(fake=FakeProvider(cost_usd=0.002), budget=BudgetTracker(1, 10, 0.8))


@pytest.fixture(autouse=True)
def _llm(monkeypatch):
    monkeypatch.setattr(settings, "llm_chain_default", "fake/a")
    monkeypatch.setattr(settings, "llm_timeout_seconds", 1.0)
    monkeypatch.setattr(langfuse_client, "_client", None)
    monkeypatch.setattr(langfuse_client, "_unavailable", False)


def test_langfuse_is_off_by_default_and_creates_no_client(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_public_key", "")
    asyncio.run(gateway().complete(MESSAGES))
    assert langfuse_client._client is None and not langfuse_client.langfuse_enabled()


def test_langfuse_needs_all_three_settings(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk")
    monkeypatch.setattr(settings, "langfuse_host", "")
    assert not langfuse_client.langfuse_enabled()


def test_langfuse_generation_joins_the_trace_and_omits_prompt_text(monkeypatch):
    fake = FakeLangfuse()
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-test")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-test")
    monkeypatch.setattr(settings, "langfuse_host", "http://langfuse.invalid")
    monkeypatch.setattr(langfuse_client, "_client", fake)

    async def flow():
        with tracing.span("api.request") as api_span:
            await gateway().complete(MESSAGES)
        return format(api_span.get_span_context().trace_id, "032x")

    trace_id = asyncio.run(flow())
    [call] = fake.calls
    assert call["trace_context"]["trace_id"] == trace_id           # same trace as the request
    assert call["as_type"] == "generation" and call["model"] == "fake/a"
    assert call["cost_details"] == {"total": 0.002} and call["usage_details"]["input"] > 0
    assert "private customer text" not in str(call)


def test_langfuse_failures_never_break_the_model_call(monkeypatch):
    class Broken:
        def start_observation(self, **kwargs):
            raise RuntimeError("langfuse down")

    monkeypatch.setattr(settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk")
    monkeypatch.setattr(settings, "langfuse_host", "http://x.invalid")
    monkeypatch.setattr(langfuse_client, "_client", Broken())
    assert asyncio.run(gateway().complete(MESSAGES)).text


def test_missing_langfuse_package_degrades_to_a_noop(monkeypatch):
    import builtins

    real_import = builtins.__import__
    monkeypatch.setattr(builtins, "__import__",
                        lambda name, *a, **k: (_ for _ in ()).throw(ImportError()) if name == "langfuse" else real_import(name, *a, **k))
    monkeypatch.setattr(settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk")
    monkeypatch.setattr(settings, "langfuse_host", "http://x.invalid")
    assert asyncio.run(gateway().complete(MESSAGES)).text
    assert langfuse_client._unavailable is True


def test_otlp_exporter_stays_disabled_without_configuration(monkeypatch):
    monkeypatch.setattr(settings, "otel_enabled", False)
    assert tracing.configure_exporters() is False
