"""Embed every public product that is new or changed (idempotent; unchanged products do no model work).

  SEMANTIC_EMBEDDING_PROVIDER=local_e5 ... DATABASE_URL=... python scripts/semantic_backfill.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from database.pg import make_engine  # noqa: E402
from semantic.backfill import run_backfill  # noqa: E402
from semantic.local_e5 import get_embedder  # noqa: E402


async def main() -> None:
    embedder = get_embedder()
    if embedder is None:
        raise SystemExit("semantic search is not configured (see semantic/local_e5.py)")
    engine = make_engine(os.environ["DATABASE_URL"])
    sessions, after, totals = async_sessionmaker(engine, expire_on_commit=False), None, {}
    while True:
        result = await run_backfill(sessions, embedder, worker_id="local-backfill", limit=50, after=after)
        after = result.pop("next_after")
        for key, value in result.items():
            totals[key] = totals.get(key, 0) + value
        if after is None:
            break
    await engine.dispose()
    print(totals)


asyncio.run(main())
