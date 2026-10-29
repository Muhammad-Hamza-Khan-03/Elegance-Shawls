import json
import logging

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import main
from configuration.config import settings
from observability import tracing

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


@pytest.fixture
def exporter():
    exp = InMemorySpanExporter()
    tracing.add_exporter(exp)
    return exp


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1000)
    return TestClient(main.create_app())


def test_scrub_text_removes_pii_and_secrets():
    text = "mail ayesha@example.com call +92 300 1234567 Bearer abc.def.ghi key " + "a1b2c3d4" * 5
    clean = tracing.scrub_text(text)
    for private in ("ayesha@example.com", "300 1234567", "abc.def.ghi", "a1b2c3d4a1b2c3d4"):
        assert private not in clean


def test_scrub_attrs_redacts_sensitive_names_and_drops_none():
    clean = tracing.scrub_attrs({"authorization": "x", "prompt": "hello", "model": "m", "skip": None, "n": 3})
    assert clean == {"authorization": "[redacted]", "prompt": "[redacted]", "model": "m", "n": 3}


def test_request_gets_trace_id_in_header_and_log(client):
    records = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    logging.getLogger("elegance.access").addHandler(handler)
    try:
        response = client.get("/health/")
    finally:
        logging.getLogger("elegance.access").removeHandler(handler)
    line = json.loads(records[-1])
    assert len(line["trace_id"]) == 32 and len(line["span_id"]) == 16
    assert response.headers["x-trace-id"] == line["trace_id"]


def test_incoming_traceparent_is_continued(client):
    response = client.get("/health/", headers={"traceparent": TRACEPARENT})
    assert response.headers["x-trace-id"] == "4bf92f3577b34da6a3ce929d0e0e4736"


def test_request_span_has_path_but_no_query_string(client, exporter):
    client.get("/health/?token=private-query&email=a@b.co")
    span = [s for s in exporter.get_finished_spans() if s.name == "http.request"][-1]
    assert span.attributes["http.target"] == "/health/"
    assert "private-query" not in str(dict(span.attributes))


def test_exporters_are_off_by_default(monkeypatch):
    monkeypatch.setattr(settings, "otel_enabled", False)
    assert tracing.configure_exporters() is False


def test_enabling_without_endpoint_keeps_exporters_off(monkeypatch):
    monkeypatch.setattr(settings, "otel_enabled", True)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert tracing.configure_exporters() is False


def test_worker_job_creates_a_span(exporter):
    import asyncio

    from workers.jobs import sample_job

    result = asyncio.run(sample_job({"job_try": 1}, "traced"))
    assert result["echo"] == "traced"
    assert any(s.name == "worker.job" and s.attributes["job"] == "sample_job" for s in exporter.get_finished_spans())


def test_token_counts_are_kept_but_token_secrets_are_redacted():
    clean = tracing.scrub_attrs({"llm.input_tokens": 12, "api_token": "abc", "access_token": "x"})
    assert clean == {"llm.input_tokens": 12, "api_token": "[redacted]", "access_token": "[redacted]"}


def test_otlp_export_reaches_a_local_collector_with_env_only_credentials(monkeypatch):
    """Exports to a local stub server: no Grafana, no real credentials."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from opentelemetry.sdk.trace import TracerProvider

    received = []

    class Collector(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path, self.headers.get("authorization"), self.rfile.read(int(self.headers["content-length"]))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "authorization=Basic fake-test-value")
    monkeypatch.setattr(settings, "otel_enabled", True)
    provider = TracerProvider()
    try:
        assert tracing.configure_exporters(provider) is True
        with provider.get_tracer("t").start_as_current_span("export.me"):
            pass
        provider.force_flush()
    finally:
        server.shutdown()
    [(path, auth, body)] = received
    assert path == "/v1/traces" and auth == "Basic fake-test-value" and b"export.me" in body


def test_exporter_is_not_attached_when_disabled_even_with_an_endpoint(monkeypatch):
    from opentelemetry.sdk.trace import TracerProvider

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:1")
    monkeypatch.setattr(settings, "otel_enabled", False)
    assert tracing.configure_exporters(TracerProvider()) is False


def test_api_and_worker_startup_call_configure_exporters(monkeypatch):
    import asyncio

    import main
    from workers import settings as worker_settings

    calls = []
    monkeypatch.setattr(main, "configure_exporters", lambda: calls.append("api"))
    monkeypatch.setattr(worker_settings, "configure_exporters", lambda: calls.append("worker"))

    async def noop(*_):
        return None

    async def flow():
        monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://u:p@127.0.0.1:1/x")
        monkeypatch.setattr(main, "connect_to_postgres", noop)
        monkeypatch.setattr(main, "close_queue_pool", noop)
        monkeypatch.setattr(main, "close_redis", noop)
        monkeypatch.setattr(main, "close_postgres", noop)
        async with main.lifespan(main.create_app()):
            pass
        await worker_settings.on_startup({})

    asyncio.run(flow())
    assert calls == ["api", "worker"]
