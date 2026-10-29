import logging
import secrets
from collections import defaultdict, deque
from time import monotonic, time

from fastapi import Request
from starlette.responses import JSONResponse

from configuration.config import settings
from database.redis_client import get_redis

logger = logging.getLogger("elegance.rate_limit")
_REDIS_RETRY_AFTER_FAILURE_SECONDS = 10.0


def _is_internal(request: Request) -> bool:
    """Public reads from the storefront server; admin routes are always limited."""
    token = settings.internal_api_token
    provided = request.headers.get("x-internal-api-token", "")
    return bool(token and provided) and secrets.compare_digest(provided, token)


class RateLimitMiddleware:
    """Redis-backed fixed-window limiter shared across replicas.

    When Redis is not configured or is down it falls back to a per-instance sliding window,
    so the API keeps working (and keeps limiting) without Redis.
    """

    def __init__(self, app):
        self.app = app
        self.requests: dict[str, deque[float]] = defaultdict(deque)
        self._redis_down_until = 0.0

    async def _hit_redis(self, key: str, limit: int) -> bool | None:
        """True = allowed, False = limited, None = Redis unavailable (use the fallback)."""
        client = get_redis()
        if client is None or monotonic() < self._redis_down_until:
            return None
        window_key = f"ratelimit:{key}:{int(time() // 60)}"
        try:
            count = await client.incr(window_key)
            if count == 1:
                await client.expire(window_key, 60)
        except Exception:
            self._redis_down_until = monotonic() + _REDIS_RETRY_AFTER_FAILURE_SECONDS
            logger.warning("Redis rate limiter unavailable; using the in-process fallback")
            return None
        return count <= limit

    def _hit_local(self, key: str, limit: int) -> bool:
        now = monotonic()
        bucket = self.requests[key]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        client = request.client.host if request.client else "unknown"
        # Event batches are anonymous POSTs with their own, tighter limit (never exempted).
        is_events = request.url.path.startswith("/v1/events")
        is_admin = not is_events and (
            request.url.path.startswith(("/products/admin", "/v1/admin")) or request.method != "GET"
        )
        limit = (
            settings.events_rate_limit_per_minute
            if is_events
            else settings.admin_rate_limit_per_minute
            if is_admin
            else settings.public_rate_limit_per_minute
        )
        if not is_admin and not is_events and _is_internal(request):
            await self.app(scope, receive, send)
            return
        key = f"{client}:{'events' if is_events else 'admin' if is_admin else 'public'}"
        allowed = await self._hit_redis(key, limit)
        if allowed is None:
            allowed = self._hit_local(key, limit)
        if not allowed:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": "60"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
