"""Optional Langfuse generation tracing for LLM calls. Off unless all three LANGFUSE_* settings are set.

Sends model, token counts, cost and latency only: never prompts or replies. The Langfuse generation
joins the OpenTelemetry trace of the request (same trace ID, request span as parent).
"""
import logging

from configuration.config import settings

logger = logging.getLogger("elegance.langfuse")
_client = None
_unavailable = False


def langfuse_enabled() -> bool:
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key and settings.langfuse_host)


def _get_client():
    global _client, _unavailable
    if _client is None and not _unavailable:
        try:
            from langfuse import Langfuse  # optional: requirements-llm.txt
        except ImportError:
            _unavailable = True
            logger.warning("LANGFUSE_* is set but the langfuse package is not installed; tracing stays off")
            return None
        _client = Langfuse(public_key=settings.langfuse_public_key, secret_key=settings.langfuse_secret_key,
                           host=settings.langfuse_host)
    return _client


def record_generation(*, model: str, logical: str, input_tokens: int, output_tokens: int, cost_usd: float,
                      latency_ms: float, trace_id: str | None, parent_span_id: str | None,
                      prompt_version: str | None = None, client=None) -> None:
    if client is None:
        if not langfuse_enabled():
            return
        client = _get_client()
        if client is None:
            return
    try:
        client.start_observation(
            trace_context={"trace_id": trace_id, "parent_span_id": parent_span_id} if trace_id else None,
            name="llm.call", as_type="generation", model=model,
            usage_details={"input": input_tokens, "output": output_tokens},
            cost_details={"total": cost_usd},
            metadata={"logical": logical, "latency_ms": latency_ms, "prompt_version": prompt_version},
        ).end()
    except Exception as exc:  # observability must never break a model call
        logger.warning("langfuse generation not recorded: %s", type(exc).__name__)
