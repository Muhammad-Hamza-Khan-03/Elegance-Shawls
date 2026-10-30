import json
import logging
import re
import sys
import uuid
from time import perf_counter

from observability.tracing import context_from_traceparent, current_ids, set_attrs, span

logger = logging.getLogger("elegance.access")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

_REQUEST_ID = re.compile(r"[A-Za-z0-9-]{8,64}")


class RequestLogMiddleware:
    """JSON access log with request IDs.

    Logs only method, path, status and latency: never headers, query strings,
    bodies or client addresses, so admin keys and customer data stay out of logs.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")
        parent = context_from_traceparent(headers.get(b"traceparent", b"").decode("latin-1"))
        request_id = incoming if _REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        started = perf_counter()
        status = 500
        trace_id = span_id = None

        async def send_with_request_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                extra = [(b"x-request-id", request_id.encode())]
                if trace_id:
                    extra.append((b"x-trace-id", trace_id.encode()))
                message["headers"] = [*message.get("headers", []), *extra]
            await send(message)

        try:
            # Path only, never the query string; scrubbed like every span attribute.
            with span("http.request", parent=parent, **{"http.method": scope["method"], "http.target": scope["path"]}) as current:
                trace_id, span_id = current_ids()
                try:
                    await self.app(scope, receive, send_with_request_id)
                finally:
                    set_attrs(current, **{"http.status_code": status})
        finally:
            logger.info(json.dumps({
                "event": "http_request",
                "request_id": request_id,
                "trace_id": trace_id,
                "span_id": span_id,
                "method": scope["method"],
                "path": scope["path"],
                "status": status,
                "duration_ms": round((perf_counter() - started) * 1000, 1),
            }))
