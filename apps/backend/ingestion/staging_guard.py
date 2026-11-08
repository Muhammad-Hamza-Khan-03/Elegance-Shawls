"""Staging-database guard with no dependency on application settings or database modules.

``--discovery-only`` must be able to run (and refuse bad database names) before any settings
object or database module is loaded.
"""
import os
import re
from urllib.parse import urlsplit

STAGING_NAME = re.compile(r"(^|[_-])staging($|[_-])", re.I)


class StagingGuardError(Exception):
    pass


def database_name(url: str) -> str:
    """The database part of a connection URL (postgresql+asyncpg://user:pw@host:5432/NAME). Never raises or echoes the URL."""
    try:
        return urlsplit(url or "").path.lstrip("/").split("?")[0]
    except ValueError:
        return ""


def assert_staging(db_name: str) -> None:
    """Refuse any database that does not clearly identify itself as staging."""
    if not STAGING_NAME.search(db_name or "") or re.search("prod", db_name, re.I):
        raise StagingGuardError("Refusing to run: database name must identify a staging database")


def prepare_discovery_environment() -> None:
    """Guard the database name, using the ignored local .env like the settings model would.

    Discovery never reads or writes the database, so no connection is made; only the name is checked.
    """
    from dotenv import load_dotenv

    load_dotenv()  # never overrides the environment
    assert_staging(database_name(os.environ.get("DATABASE_URL", "")))


def assert_staging_run(optin_var: str, environ=None) -> None:
    """Seed/backfill guard: ENVIRONMENT must be exactly "staging" (unset or unknown refuses), ``optin_var`` must be "true", and the database must be a staging one."""
    environ = os.environ if environ is None else environ
    if environ.get("ENVIRONMENT", "").strip().lower() != "staging":
        raise StagingGuardError("Refusing to run: ENVIRONMENT must be explicitly set to staging")
    if environ.get(optin_var, "").strip().lower() != "true":
        raise StagingGuardError(f"Refusing to run: {optin_var}=true is required")
    assert_staging(database_name(environ.get("DATABASE_URL", "")))
