import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from configuration.config import settings
from database.pg import make_engine
from models.relational_model import Base

target_metadata = Base.metadata


def _url() -> str:
    # A URL set on the Alembic config (tests) wins over the environment.
    url = context.config.get_main_option("sqlalchemy.url") or settings.database_url
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = make_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
