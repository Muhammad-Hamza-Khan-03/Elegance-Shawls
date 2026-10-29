import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from configuration.config import settings
from database import pg


async def _db_up():
    return True


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1000)
    monkeypatch.setattr(main, "database_is_ready", _db_up)
    monkeypatch.setattr(pg, "_engine", None)
    monkeypatch.setattr(pg, "_sessions", None)


def test_session_dependency_is_503_when_postgres_not_initialised():
    async def consume():
        async for _ in pg.get_pg_session():
            pass

    with pytest.raises(HTTPException) as error:
        asyncio.run(consume())
    assert error.value.status_code == 503


def test_connect_is_noop_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")
    assert asyncio.run(pg.connect_to_postgres()) is False
    assert asyncio.run(pg.postgres_is_ready()) is False


def test_connect_returns_false_when_unreachable(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://u:p@127.0.0.1:1/db")
    monkeypatch.setattr(settings, "pg_connect_timeout_seconds", 0.2)

    async def attempt():
        try:
            return await pg.connect_to_postgres()
        finally:
            await pg.close_postgres()

    assert asyncio.run(attempt()) is False


def test_ready_reports_postgres_as_the_database_and_optional_services_as_disabled():
    body = TestClient(main.create_app()).get("/ready/").json()
    assert body == {"status": "ready", "database": "connected", "postgres": "connected", "redis": "disabled", "worker": "disabled"}


def test_ready_is_503_when_postgres_is_down(monkeypatch):
    async def down(timeout_seconds=2.0):
        return False

    monkeypatch.setattr(main, "database_is_ready", down)
    response = TestClient(main.create_app()).get("/ready/")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}


def test_data_routes_answer_503_not_500_when_postgres_is_unavailable():
    client = TestClient(main.create_app())            # PostgreSQL never initialised in this process
    assert client.get("/products/").status_code == 503
    assert client.get("/products/slug/anything").status_code == 503


def test_startup_requires_database_url(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")

    async def start():
        async with main.lifespan(main.create_app()):
            pass

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        asyncio.run(start())


def test_startup_survives_an_unreachable_database_and_reports_not_ready(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://u:p@127.0.0.1:1/db")
    monkeypatch.setattr(settings, "pg_connect_timeout_seconds", 0.2)

    async def start():
        async with main.lifespan(main.create_app()):
            return await pg.postgres_is_ready()   # (main.database_is_ready is stubbed by the autouse fixture)

    assert asyncio.run(start()) is False


def test_health_is_dependency_free(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://u:p@127.0.0.1:1/db")
    assert TestClient(main.create_app()).get("/health/").json() == {"status": "ok"}
