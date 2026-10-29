"""Request/worker/LLM tracing on OpenTelemetry, with PII scrubbing. No exporter by default.

A private TracerProvider (never the global one) means spans always carry valid trace IDs for
log correlation, while nothing leaves the process unless OTEL_ENABLED=true and an OTLP endpoint
is configured. Span attributes pass through scrub_attrs; prompts and message bodies are never
recorded.
"""
import logging
import os
import re
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from configuration.config import settings

logger = logging.getLogger("elegance.tracing")

_provider = TracerProvider(resource=Resource.create({"service.name": "elegance-backend"}))
_propagator = TraceContextTextMapPropagator()
_configured = False

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)")
_BEARER = re.compile(r"(?i)bearer\s+[\w.~+/=-]+")
_TOKEN = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")
_SENSITIVE_KEYS = ("key", "token", "secret", "password", "authorization", "cookie", "prompt", "content", "message")
REDACTED = "[redacted]"


def scrub_text(value: str) -> str:
    for pattern in (_BEARER, _EMAIL, _TOKEN, _PHONE):
        value = pattern.sub(REDACTED, value)
    return value


def scrub_attrs(attrs: dict) -> dict:
    clean = {}
    for name, value in attrs.items():
        if value is None:
            continue
        lowered = name.lower()
        # "input_tokens" is a count, not a credential.
        if any(part in lowered for part in _SENSITIVE_KEYS) and not lowered.endswith("tokens"):
            clean[name] = REDACTED
        else:
            clean[name] = scrub_text(value) if isinstance(value, str) else value
    return clean


def get_tracer() -> trace.Tracer:
    return _provider.get_tracer("elegance")


def add_exporter(exporter: SpanExporter, batch: bool = False, provider: TracerProvider | None = None) -> None:
    (provider or _provider).add_span_processor((BatchSpanProcessor if batch else SimpleSpanProcessor)(exporter))


def configure_exporters(provider: TracerProvider | None = None) -> bool:
    """Attach an OTLP exporter only when explicitly enabled; failures never affect the app."""
    global _configured
    if (_configured and provider is None) or not settings.otel_enabled:
        return False
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        logger.warning("OTEL_ENABLED is set but OTEL_EXPORTER_OTLP_ENDPOINT is empty; exporters stay off")
        return False
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    except ImportError:
        logger.warning("OTLP exporter package is not installed; exporters stay off")
        return False
    # Endpoint and credentials (OTEL_EXPORTER_OTLP_ENDPOINT / _HEADERS) are read from the environment only.
    add_exporter(OTLPSpanExporter(), batch=True, provider=provider)
    _configured = _configured or provider is None
    return True


def context_from_traceparent(traceparent: str | None):
    return _propagator.extract({"traceparent": traceparent}) if traceparent else None


def current_traceparent() -> str | None:
    """W3C traceparent for the active span, to carry across Redis/arq job payloads."""
    carrier: dict[str, str] = {}
    _propagator.inject(carrier)
    return carrier.get("traceparent")


def set_attrs(current, **attrs) -> None:
    for name, value in scrub_attrs(attrs).items():
        current.set_attribute(name, value)


@contextmanager
def span(name: str, parent=None, **attrs):
    with get_tracer().start_as_current_span(name, context=parent, record_exception=False) as current:
        set_attrs(current, **attrs)
        yield current


def current_ids() -> tuple[str | None, str | None]:
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None, None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
