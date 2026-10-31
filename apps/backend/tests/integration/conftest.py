"""Real PostgreSQL (pgvector) and Redis via Testcontainers. Skipped cleanly without Docker."""
import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.pg import make_engine

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PG_IMAGE = "pgvector/pgvector:0.8.1-pg17"
APP_USER, APP_PASSWORD = "app_role", "app-role-test-password"
TABLES = ("customer_sessions, memory_items, memory_consents, action_executions, embedding_jobs, product_embeddings, enquiries, admin_sessions, admin_accounts, staged_product_audit, staged_products, ingestion_jobs, variants, products, "
          "outbox, audit_log, events, tool_calls, messages, conversations, customer_identities, customers")


def pytest_collection_modifyitems(items):
    for item in items:
        if "tests/integration" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def docker_client():
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return client
    except Exception as exc:  # no Docker: skip, never fail
        pytest.skip(f"Docker is unavailable: {exc}")


@pytest.fixture(scope="session")
def pg_container(docker_client):
    from testcontainers.postgres import PostgresContainer

    container = (
        PostgresContainer(PG_IMAGE, username="admin_role", password="admin-role-test-password", dbname="elegance_test")
        .with_env("POSTGRES_APP_USER", APP_USER)
        .with_env("POSTGRES_APP_PASSWORD", APP_PASSWORD)
        .with_env("POSTGRES_BACKUP_USER", "backup_role")
        .with_env("POSTGRES_BACKUP_PASSWORD", "backup-role-test-password")
        .with_volume_mapping(
            str(BACKEND_ROOT.parents[1] / "deploy/postgres/init-roles.sh"),
            "/docker-entrypoint-initdb.d/10-init-roles.sh",
            "ro",
        )
    )
    with container:
        yield container


def _url(container, user: str, password: str) -> str:
    return (
        f"postgresql+asyncpg://{user}:{password}@{container.get_container_host_ip()}:"
        f"{container.get_exposed_port(5432)}/elegance_test"
    )


@pytest.fixture(scope="session")
def pg_url(pg_container) -> str:
    """Connects as the least-privilege application role created by the init script."""
    return _url(pg_container, APP_USER, APP_PASSWORD)


@pytest.fixture(scope="session")
def backup_url(pg_container) -> str:
    return _url(pg_container, "backup_role", "backup-role-test-password")


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def migrated_url(pg_url) -> str:
    command.upgrade(alembic_config(pg_url), "head")
    return pg_url


@pytest.fixture
def pg_engine_factory(migrated_url):
    """Engines are created inside each test's event loop; truncation runs before every test."""
    async def truncate():
        engine = make_engine(migrated_url)
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
        await engine.dispose()

    asyncio.run(truncate())
    return lambda: make_engine(migrated_url)


@pytest.fixture(scope="session")
def redis_url(docker_client):
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7.4-alpine") as container:
        yield f"redis://{container.get_container_host_ip()}:{container.get_exposed_port(6379)}/0"


@pytest_asyncio.fixture
async def db(migrated_url):
    """Async tests: a clean migrated database and a handle on it (engine lives in the test's own loop)."""
    from tests.integration.ingest_support import Db

    engine = make_engine(migrated_url)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    yield Db(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()
