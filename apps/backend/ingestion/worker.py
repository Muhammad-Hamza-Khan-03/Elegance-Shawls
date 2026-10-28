"""Ingestion worker: `python -m ingestion.worker`. Runs separately from the API process."""
import asyncio
import logging
import os
import socket

from ingestion import jobs
from ingestion.normalize import InvalidSourceData
from ingestion.pipeline import run_job
from ingestion.quill_scraper import ExtractorNotConfigured, FieldExtractor, UnconfiguredExtractor
from ingestion.safe_fetch import FetchError, SafeFetcher

logger = logging.getLogger("ingestion.worker")
NON_RETRYABLE = (InvalidSourceData, ExtractorNotConfigured)


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


async def process_next_job(db, me: str, fetcher: SafeFetcher, extractor: FieldExtractor) -> dict | None:
    """Recover stale leases, claim one job and run it. Returns the final job document, if any."""
    await jobs.recover_expired_leases(db)
    job = await jobs.claim_next(db, me)
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
    # A real FieldExtractor must be wired here once the source's markup is agreed.
    extractor = UnconfiguredExtractor()
    while True:
        if not await process_next_job(db, me, fetcher, extractor):
            await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
