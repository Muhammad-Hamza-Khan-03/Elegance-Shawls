"""Ingestion worker: `python -m ingestion.worker`. Runs separately from the API process."""
import asyncio
import json
import logging
import os
import socket
from typing import TYPE_CHECKING

# Settings, database and fetching modules are imported lazily so that `--discovery-only` can run
# (and reject a bad database name) without database credentials or database modules.
if TYPE_CHECKING:
    from ingestion.quill_scraper import FieldExtractor
    from ingestion.safe_fetch import SafeFetcher

logger = logging.getLogger("ingestion.worker")


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


async def process_next_job(sessions, me: str, fetcher: "SafeFetcher", extractor: "FieldExtractor",
                           only_ids: list | None = None):
    """Recover stale leases, claim one job and run it. Returns the final job row, if any.

    Claim, run and complete are separate short transactions: the claim commits (releasing its row
    lock) before any HTTP fetch, and nothing holds a database transaction while the page is fetched.
    """
    from ingestion.normalize import InvalidSourceData
    from ingestion.pipeline import run_job
    from ingestion.quill_scraper import ExtractorNotConfigured
    from ingestion.safe_fetch import FetchError
    from repositories import jobs

    async with sessions() as session, session.begin():
        await jobs.recover_expired_leases(session)
    async with sessions() as session, session.begin():
        job = await jobs.claim_next(session, me, only_ids=only_ids)
    if not job:
        return None

    async def settle(**failure):
        async with sessions() as session, session.begin():
            return await jobs.fail_job(session, job.id, me, **failure)

    try:
        result = await run_job(sessions, job, fetcher=fetcher, extractor=extractor)
    except FetchError as exc:
        return await settle(error=str(exc), retryable=exc.retryable)
    except (InvalidSourceData, ExtractorNotConfigured) as exc:
        return await settle(error=str(exc), retryable=False)
    except Exception:
        logger.exception("unexpected error in job %s", job.id)
        return await settle(error="Unexpected internal error", retryable=True)
    async with sessions() as session, session.begin():
        return await jobs.complete_job(session, job.id, me, result)


async def main(poll_seconds: float = 5.0) -> None:
    from database.pg import close_postgres, connect_to_postgres, postgres_configured, session_factory
    from ingestion.extractors import ShopifyHtmlExtractor
    from ingestion.safe_fetch import SafeFetcher

    if not postgres_configured():
        raise SystemExit("DATABASE_URL is required: ingestion jobs live in PostgreSQL")
    await connect_to_postgres()
    sessions, me, fetcher = session_factory(), worker_id(), SafeFetcher()
    extractor = ShopifyHtmlExtractor()
    try:
        while True:
            if not await process_next_job(sessions, me, fetcher, extractor):
                await asyncio.sleep(poll_seconds)
    finally:
        await close_postgres()


def parse_args(argv: list[str] | None = None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m ingestion.worker",
        description="Without flags: long-running worker. With a flag: one bounded run that then exits.")
    parser.add_argument("--once", action="store_true", help="refresh all authorized sources, then exit")
    parser.add_argument("--dry-run", action="store_true", help="plan the refresh; no database writes")
    parser.add_argument("--discovery-only", action="store_true", help="read sitemaps only; no database access")
    parser.add_argument("--summary-file", help="also write the sanitized JSON summary to this path")
    parser.add_argument("--product-path", action="append", default=[], metavar="PATH",
                        help="explicit /products/<handle> path; repeat up to five times")
    parser.add_argument("--product-url", action="append", default=[], metavar="URL",
                        help="explicit HTTPS product URL; repeat up to five times")
    args = parser.parse_args(argv)
    if args.product_path and args.product_url:
        parser.error("--product-path and --product-url cannot be mixed")
    if len(args.product_path) > 5 or len(args.product_url) > 5:
        parser.error("at most five explicit products are allowed")
    if (args.product_path or args.product_url) and not (args.once or args.dry_run or args.discovery_only):
        parser.error("explicit product selection requires --once, --dry-run, or --discovery-only")
    return args


if __name__ == "__main__":
    args = parse_args()
    if args.discovery_only:
        from ingestion.staging_guard import StagingGuardError, prepare_discovery_environment

        try:
            prepare_discovery_environment()
        except StagingGuardError as exc:
            print(json.dumps({"termination_reason": "staging_guard_failed", "error": str(exc)}, indent=2))
            raise SystemExit(1)
    if args.once or args.dry_run or args.discovery_only:
        from ingestion.refresh import run_cli

        mode = "discovery-only" if args.discovery_only else "dry-run" if args.dry_run else "once"
        raise SystemExit(asyncio.run(run_cli(
            mode, args.summary_file, product_paths=args.product_path, product_urls=args.product_url,
        )))
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
