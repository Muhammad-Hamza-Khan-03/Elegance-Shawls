"""Staging-database guard with no dependency on application settings or database modules.

``--discovery-only`` must be able to run (and refuse bad database names) before any settings
object, MongoDB driver or database module is loaded.
"""
import os
import re

STAGING_NAME = re.compile(r"(^|[_-])staging($|[_-])", re.I)


class StagingGuardError(Exception):
    pass


def assert_staging(db_name: str) -> None:
    """Refuse any database that does not clearly identify itself as staging."""
    if not STAGING_NAME.search(db_name or "") or re.search("prod", db_name, re.I):
        raise StagingGuardError("Refusing to run: database name must identify a staging database")


def prepare_discovery_environment() -> None:
    """Guard the database name, then let the shared settings model load without MongoDB credentials.

    Discovery never reads or writes MongoDB, so a blank URI is supplied only when none is
    configured. The API and every other mode keep the strict required-field behaviour.
    """
    from dotenv import load_dotenv

    load_dotenv()  # same ignored local .env the settings model would read; never overrides the environment
    assert_staging(os.environ.get("MONGO_DB_NAME", ""))
    os.environ.setdefault("MONGODB_URI", "")
