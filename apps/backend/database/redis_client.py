"""Optional Redis client for arq jobs and shared rate limits. Never gates startup."""
import asyncio

from redis.asyncio import Redis

from configuration.config import settings

_client: Redis | None = None


def redis_configured() -> bool:
    return bool(settings.redis_url)


def get_redis() -> Redis | None:
    """Lazily built so importing the app needs no Redis; None when disabled."""
    global _client
    if _client is None and redis_configured():
        _client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.redis_connect_timeout_seconds,
            socket_timeout=settings.redis_connect_timeout_seconds,
        )
    return _client


async def redis_is_ready(timeout_seconds: float = 1.0) -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(await asyncio.wait_for(client.ping(), timeout_seconds))
    except Exception:
        return False


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None
