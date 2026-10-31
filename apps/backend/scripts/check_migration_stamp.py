"""Read-only: does this database carry the pre-consolidation migration numbering? Never stamps, upgrades or writes.

Before `staging-integration` the integration branch numbered its own migrations 0007-0012 (admin accounts, enquiries, semantic
embeddings, action executions, customer memory, customer sessions) while main used 0007-0009 for attributes, enrichment and embeddings.
They now run 0010-0015. A database stamped under the old numbering would be upgraded from the wrong place (or crash on a table that
already exists), and stamping it to a revision it has not truly reached would hide that. Exit 0: stamp is consistent; 3: legacy.

  DATABASE_URL=postgresql+asyncpg://... python scripts/check_migration_stamp.py
"""
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

LEGACY_HELP = """legacy numbering detected: {why}
Do NOT `alembic stamp` and do NOT `alembic upgrade head` on this database.
  * Disposable development database (seed data only): drop it and run `alembic upgrade head` on a new one, then scripts/seed_local.py.
  * Anything you must keep: `pg_dump` it first, restore into a new database, drop the legacy `product_embeddings` (content_hash schema, rebuildable
    with scripts/embedding_backfill.py), and stamp only the revision the remaining schema really matches - see docs/STAGING_CONSOLIDATION.md."""


async def inspect(url: str) -> tuple[str | None, str | None]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            version = (await conn.execute(text("select version_num from alembic_version"))).scalar_one_or_none()
            tables = {r[0] for r in await conn.execute(text("select table_name from information_schema.tables where table_schema = 'public'"))}
            cols = {r[0] for r in await conn.execute(text(
                "select column_name from information_schema.columns where table_name = 'product_embeddings'"))}
    finally:
        await engine.dispose()
    if version is None or version not in {f"{i:04d}" for i in range(7, 13)}:
        return version, None
    if "content_hash" in cols:
        return version, "product_embeddings has the old semantic schema (content_hash)"
    if "admin_accounts" in tables and version < "0010":
        return version, f"admin_accounts exists but the stamp is {version} (< 0010)"
    return version, None


def main() -> int:
    version, why = asyncio.run(inspect(os.environ["DATABASE_URL"]))
    if why:
        print(LEGACY_HELP.format(why=why), file=sys.stderr)
        return 3
    print(f"migration stamp {version or 'none'} is consistent with this branch's numbering")
    return 0


if __name__ == "__main__":
    sys.exit(main())
