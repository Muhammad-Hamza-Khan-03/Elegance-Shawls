from collections import defaultdict, deque
from time import monotonic

from fastapi import Request
from starlette.responses import JSONResponse

from configuration.config import settings


class RateLimitMiddleware:
    """Small single-instance limiter; edge/proxy limits should supplement it in production."""

    def __init__(self, app):
        self.app = app
        self.requests: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        client = request.client.host if request.client else "unknown"
        is_admin = request.url.path.startswith("/products/admin") or request.method != "GET"
        limit = (
            settings.admin_rate_limit_per_minute
            if is_admin
            else settings.public_rate_limit_per_minute
        )
        key = f"{client}:{'admin' if is_admin else 'public'}"
        now = monotonic()
        bucket = self.requests[key]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= limit:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": "60"},
            )
            await response(scope, receive, send)
            return
        bucket.append(now)
        await self.app(scope, receive, send)
