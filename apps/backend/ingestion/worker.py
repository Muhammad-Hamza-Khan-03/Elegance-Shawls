"""Ingestion worker: `python -m ingestion.worker`. Runs separately from the API process."""
import asyncio
import logging
import os
import socket

from ingestion import jobs
from ingestion.normalize import InvalidSourceData
from ingestion.pipeline import run_job
from ingestion.extractors import ShopifyHtmlExtractor
from ingestion.quill_scraper import ExtractorNotConfigured, FieldExtractor
from ingestion.safe_fetch import FetchError, SafeFetcher

logger = logging.getLogger("ingestion.worker")
NON_RETRYABLE = (InvalidSourceData, ExtractorNotConfigured)


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


async def process_next_job(db, me: str, fetcher: SafeFetcher, extractor: FieldExtractor,
                           only_ids: list | None = None) -> dict | None:
    """Recover stale leases, claim one job and run it. Returns the final job document, if any."""
    await jobs.recover_expired_leases(db)
    job = await jobs.claim_next(db, me, only_ids=only_ids)
    if not job:
        return None
    try:
        result = await run_job(db, job, fetcher=fetcher, extractor=extractor)
    except FetchError as exc:
        return await jobs.fail_job(db, job["_id"], me, str(exc), retryable=exc.retryable)
    except NON_RETRYABLE as exc:
        return await jobs.fail_job(db, job["_id"], me, str(exc), retryable=False)
    except Exception:
        logger.exception("unexpected error in job %s", job["_id"])
        return await jobs.fail_job(db, job["_id"], me, "Unexpected internal error", retryable=True)
    return await jobs.complete_job(db, job["_id"], me, result)


async def main(poll_seconds: float = 5.0) -> None:
    from database.db import connect_to_mongo, get_db

    await connect_to_mongo()
    db, me, fetcher = get_db(), worker_id(), SafeFetcher()
    extractor = ShopifyHtmlExtractor()
    while True:
        if not await process_next_job(db, me, fetcher, extractor):
            await asyncio.sleep(poll_seconds)


def parse_args(argv: list[str] | None = None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m ingestion.worker",
        description="Without flags: long-running worker. With a flag: one bounded run that then exits.")
    parser.add_argument("--once", action="store_true", help="refresh all authorized sources, then exit")
    parser.add_argument("--dry-run", action="store_true", help="plan the refresh; no MongoDB writes")
    parser.add_argument("--discovery-only", action="store_true", help="read sitemaps only; no MongoDB access")
    parser.add_argument("--summary-file", help="also write the sanitized JSON summary to this path")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    if args.once or args.dry_run or args.discovery_only:
        from ingestion.refresh import run_cli

        mode = "discovery-only" if args.discovery_only else "dry-run" if args.dry_run else "once"
        raise SystemExit(asyncio.run(run_cli(mode, args.summary_file)))
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
