"""PostgreSQL layer: the sole database. An unreachable server never crashes startup (/ready/ reports 503); a missing DATABASE_URL does."""
import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from configuration.config import settings
from observability.db_tracing import instrument_engine

logger = logging.getLogger("elegance.database")

_engine: AsyncEngine | None = None
_sessions: async_sessionmaker[AsyncSession] | None = None


def postgres_configured() -> bool:
    return bool(settings.database_url)


def make_engine(url: str | None = None) -> AsyncEngine:
    return instrument_engine(create_async_engine(
        url or settings.database_url,
        pool_size=settings.pg_pool_size,
        max_overflow=settings.pg_max_overflow,
        pool_timeout=settings.pg_pool_timeout_seconds,
        pool_pre_ping=True,
        connect_args={"timeout": settings.pg_connect_timeout_seconds},
    ))


async def connect_to_postgres() -> bool:
    """Create the engine and ping once. Returns False (never raises) so the API can still serve."""
    global _engine, _sessions
    if not postgres_configured():
        return False
    _engine = make_engine()
    _sessions = async_sessionmaker(_engine, expire_on_commit=False)
    if not await postgres_is_ready():
        logger.warning("PostgreSQL is configured but unreachable; AI/events features are degraded")
        return False
    return True


async def postgres_is_ready(timeout_seconds: float = 2.0) -> bool:
    if _engine is None:
        return False
    try:
        async def ping() -> None:
            async with _engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

        await asyncio.wait_for(ping(), timeout_seconds)
        return True
    except Exception:
        return False


# main.py's /ready/ and the transitional runtime call this name; it is PostgreSQL now.
database_is_ready = postgres_is_ready


def session_factory() -> async_sessionmaker[AsyncSession]:
    """For code that opens several short transactions (the ingestion worker)."""
    if _sessions is None:
        raise RuntimeError("PostgreSQL is not initialised")
    return _sessions


async def close_postgres() -> None:
    global _engine, _sessions
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessions = None


def open_session() -> AsyncSession | None:
    """A session for best-effort background writes; None when PostgreSQL is not initialised."""
    return _sessions() if _sessions is not None else None


async def get_pg_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. 503 when PostgreSQL is not configured or not initialised."""
    if _sessions is None:
        raise HTTPException(status_code=503, detail="PostgreSQL is not available")
    async with _sessions() as session:
        yield session
