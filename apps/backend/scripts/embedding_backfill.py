"""Bounded, resumable embedding backfill for the single approved catalogue. Never runs at startup; --limit is required.

  python scripts/embedding_backfill.py --kind product --limit 100 --dry-run     # report only, nothing written
  python scripts/embedding_backfill.py --kind product --limit 100 [--after UUID] # uses DATABASE_URL, EMBEDDING_* settings
Run from apps/backend. Examines at most --limit public live owners in id order after the resume cursor, creates the
missing queued rows (idempotent by identity key) and embeds them inline, one at a time. The summary's `last_id` is the
next --after. Rerunning is safe: finished rows are skipped, failed rows stay failed until the source changes.
"""
import argparse
import asyncio
import json
import sys
import uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from configuration.config import settings  # noqa: E402
from repositories import embeddings as repo  # noqa: E402
from search import embedding_service  # noqa: E402
from search.providers import EmbeddingProvider, provider_for  # noqa: E402


async def backfill(sessions: async_sessionmaker, provider: EmbeddingProvider, *, kind: str, limit: int,
                   dry_run: bool, after: uuid.UUID | None = None) -> dict:
    if not 1 <= limit <= settings.embedding_backfill_max_limit:
        raise ValueError(f"--limit must be between 1 and {settings.embedding_backfill_max_limit}")
    counts: Counter = Counter(examined=0)
    async with sessions() as session:
        ids = await repo.live_owner_ids(session, kind, after, limit)
    for owner_id in ids:
        counts["examined"] += 1
        try:
            async with sessions() as session:
                row, created = await embedding_service.ensure_pending(
                    session, kind, owner_id, provider, index_version=settings.embedding_index_version,
                    max_attempts=settings.embedding_max_attempts)
                await (session.rollback() if dry_run else session.commit())
        except ValueError:  # text that cannot be represented (for example too long): fix the catalogue field
            counts["unrepresentable"] += 1
            continue
        if row is None:  # went non-public since the page was read
            counts["not_public"] += 1
        elif created:
            counts["would_create" if dry_run else "created"] += 1
        if row is None or dry_run:
            continue
        if row.status in ("succeeded", "failed", "stale"):
            counts[f"already_{row.status}"] += 1
            continue
        result = await embedding_service.process(sessions, provider, kind, row.id, lease_seconds=settings.embedding_lease_seconds,
                                                 backoff_seconds=settings.embedding_backoff_seconds)
        counts[result["status"]] += 1
    return {"kind": kind, "dry_run": dry_run, **counts, "last_id": str(ids[-1]) if ids else None}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kind", choices=("product", "variant"), required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--after", type=uuid.UUID, help="resume after this owner id (the last_id of a previous run)")
    parser.add_argument("--scope", default=settings.ingestion_source_id, help="only the single approved catalogue exists")
    args = parser.parse_args()
    if args.scope != settings.ingestion_source_id:
        print(f"unknown scope {args.scope!r}", file=sys.stderr)
        return 2
    if not args.dry_run and not settings.embedding_enabled:
        print("EMBEDDING_ENABLED is false; use --dry-run or enable it deliberately", file=sys.stderr)
        return 2
    from database.pg import make_engine, postgres_configured

    if not postgres_configured():
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    provider = provider_for(settings.embedding_provider, settings.embedding_dimensions)
    engine = make_engine()
    try:
        summary = await backfill(async_sessionmaker(engine, expire_on_commit=False), provider, kind=args.kind,
                                 limit=args.limit, dry_run=args.dry_run, after=args.after)
    finally:
        await engine.dispose()
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
