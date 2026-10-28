import json
import logging
import re
import sys
import uuid
from time import perf_counter

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

        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        started = perf_counter()
        status = 500

        async def send_with_request_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [*message.get("headers", []), (b"x-request-id", request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            logger.info(json.dumps({
                "event": "http_request",
                "request_id": request_id,
                "method": scope["method"],
                "path": scope["path"],
                "status": status,
                "duration_ms": round((perf_counter() - started) * 1000, 1),
            }))
