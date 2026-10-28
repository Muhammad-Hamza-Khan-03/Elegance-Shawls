"""Durable, MongoDB-backed ingestion jobs.

Claiming, completion and failure are single conditional updates so two workers can never
own the same job, and a worker that lost its lease cannot overwrite a newer outcome.
"""
import hashlib
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from configuration.config import settings
from schemas.ingestion_schema import JobStatus

CLAIMABLE = [JobStatus.QUEUED.value, JobStatus.RETRYING.value]
MAX_ERROR_LENGTH = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def idempotency_key_for(source_id: str, path: str) -> str:
    return hashlib.sha256(f"{source_id}\n{path}".encode()).hexdigest()


def _clip(message: str) -> str:
    return message[:MAX_ERROR_LENGTH]


async def create_job(
    db,
    *,
    source_id: str,
    path: str,
    idempotency_key: str | None = None,
    max_attempts: int | None = None,
    now: datetime | None = None,
) -> tuple[dict, bool]:
    """Create a job, or return the existing one for this idempotency key. -> (job, created)."""
    ts = now or _now()
    key = idempotency_key or idempotency_key_for(source_id, path)
    document = {
        "_id": ObjectId(),
        "source_id": source_id,
        "path": path,
        "idempotency_key": key,
        "status": JobStatus.QUEUED.value,
        "attempts": 0,
        "max_attempts": max_attempts or settings.ingestion_job_max_attempts,
        "available_at": ts,
        "lease_owner": None,
        "lease_expires_at": None,
        "heartbeat_at": None,
        "cancel_requested": False,
        "last_error": None,
        "result": None,
        "created_at": ts,
        "updated_at": ts,
        "started_at": None,
        "finished_at": None,
    }
    try:
        await db.ingestion_jobs.insert_one(document)
        return document, True
    except DuplicateKeyError:
        return await db.ingestion_jobs.find_one({"idempotency_key": key}), False


async def requeue_job(db, job_id: ObjectId, now: datetime | None = None) -> dict | None:
    """Explicit rerun of a finished job. Staging is idempotent, so reruns never duplicate."""
    ts = now or _now()
    return await db.ingestion_jobs.find_one_and_update(
        {"_id": job_id, "status": {"$in": [
            JobStatus.FAILED.value, JobStatus.CANCELLED.value, JobStatus.SUCCEEDED.value]}},
        {"$set": {
            "status": JobStatus.QUEUED.value, "attempts": 0, "available_at": ts,
            "lease_owner": None, "lease_expires_at": None, "cancel_requested": False,
            "last_error": None, "finished_at": None, "updated_at": ts,
        }},
        return_document=ReturnDocument.AFTER,
    )


async def claim_next(db, worker_id: str, now: datetime | None = None, only_ids: list | None = None) -> dict | None:
    """Claim the next due job; ``only_ids`` limits a one-shot run to its own batch."""
    ts = now or _now()
    query = {"status": {"$in": CLAIMABLE}, "available_at": {"$lte": ts}, "cancel_requested": False}
    if only_ids is not None:
        query["_id"] = {"$in": list(only_ids)}
    return await db.ingestion_jobs.find_one_and_update(
        query,
        {
            "$set": {
                "status": JobStatus.RUNNING.value,
                "lease_owner": worker_id,
                "lease_expires_at": ts + timedelta(seconds=settings.ingestion_job_lease_seconds),
                "heartbeat_at": ts,
                "started_at": ts,
                "updated_at": ts,
            },
            "$inc": {"attempts": 1},
        },
        sort=[("available_at", 1), ("_id", 1)],
        return_document=ReturnDocument.AFTER,
    )


async def heartbeat(db, job_id: ObjectId, worker_id: str, now: datetime | None = None) -> bool:
    ts = now or _now()
    result = await db.ingestion_jobs.update_one(
        {"_id": job_id, "status": JobStatus.RUNNING.value, "lease_owner": worker_id},
        {"$set": {
            "heartbeat_at": ts, "updated_at": ts,
            "lease_expires_at": ts + timedelta(seconds=settings.ingestion_job_lease_seconds),
        }},
    )
    return result.modified_count == 1


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=settings.ingestion_job_backoff_seconds * (2 ** max(attempts - 1, 0)))


async def complete_job(db, job_id: ObjectId, worker_id: str, result: dict,
                       now: datetime | None = None) -> dict | None:
    ts = now or _now()
    owned = {"_id": job_id, "status": JobStatus.RUNNING.value, "lease_owner": worker_id}
    done = await db.ingestion_jobs.find_one_and_update(
        {**owned, "cancel_requested": False},
        {"$set": {"status": JobStatus.SUCCEEDED.value, "result": result, "last_error": None,
                  "lease_owner": None, "lease_expires_at": None,
                  "finished_at": ts, "updated_at": ts}},
        return_document=ReturnDocument.AFTER,
    )
    if done:
        return done
    return await _cancel_if_requested(db, owned, ts)


async def fail_job(db, job_id: ObjectId, worker_id: str, error: str, *, retryable: bool,
                   now: datetime | None = None) -> dict | None:
    """Retry with exponential backoff while attempts remain; otherwise fail terminally."""
    ts = now or _now()
    owned = {"_id": job_id, "status": JobStatus.RUNNING.value, "lease_owner": worker_id}
    job = await db.ingestion_jobs.find_one(owned)
    if not job:
        return None
    if job["cancel_requested"]:
        return await _cancel_if_requested(db, owned, ts)
    release = {"lease_owner": None, "lease_expires_at": None, "last_error": _clip(error),
               "last_error_retryable": retryable, "updated_at": ts}
    if retryable and job["attempts"] < job["max_attempts"]:
        update = {**release, "status": JobStatus.RETRYING.value, "available_at": ts + _backoff(job["attempts"])}
    else:
        update = {**release, "status": JobStatus.FAILED.value, "finished_at": ts}
    return await db.ingestion_jobs.find_one_and_update(
        owned, {"$set": update}, return_document=ReturnDocument.AFTER)


async def _cancel_if_requested(db, owned: dict, ts: datetime) -> dict | None:
    return await db.ingestion_jobs.find_one_and_update(
        {**owned, "cancel_requested": True},
        {"$set": {"status": JobStatus.CANCELLED.value, "lease_owner": None,
                  "lease_expires_at": None, "finished_at": ts, "updated_at": ts}},
        return_document=ReturnDocument.AFTER,
    )


async def recover_expired_leases(db, now: datetime | None = None) -> int:
    """Return jobs whose worker stopped heartbeating to the queue, or fail them when out of attempts."""
    ts = now or _now()
    expired = {"status": JobStatus.RUNNING.value, "lease_expires_at": {"$lt": ts}}
    recovered = 0
    async for job in db.ingestion_jobs.find(expired):
        if job["cancel_requested"]:
            update = {"status": JobStatus.CANCELLED.value, "finished_at": ts}
        elif job["attempts"] >= job["max_attempts"]:
            update = {"status": JobStatus.FAILED.value, "finished_at": ts,
                      "last_error": "Lease expired after final attempt"}
        else:
            update = {"status": JobStatus.RETRYING.value, "available_at": ts + _backoff(job["attempts"]),
                      "last_error": "Lease expired; worker presumed stopped"}
        result = await db.ingestion_jobs.update_one(
            {"_id": job["_id"], "status": JobStatus.RUNNING.value, "lease_owner": job["lease_owner"]},
            {"$set": {**update, "lease_owner": None, "lease_expires_at": None, "updated_at": ts}},
        )
        recovered += result.modified_count
    return recovered


async def cancel_job(db, job_id: ObjectId, now: datetime | None = None) -> dict | None:
    """Queued/retrying jobs cancel immediately; running ones stop at the worker's next checkpoint."""
    ts = now or _now()
    cancelled = await db.ingestion_jobs.find_one_and_update(
        {"_id": job_id, "status": {"$in": CLAIMABLE}},
        {"$set": {"status": JobStatus.CANCELLED.value, "cancel_requested": True,
                  "finished_at": ts, "updated_at": ts}},
        return_document=ReturnDocument.AFTER,
    )
    if cancelled:
        return cancelled
    return await db.ingestion_jobs.find_one_and_update(
        {"_id": job_id, "status": JobStatus.RUNNING.value},
        {"$set": {"cancel_requested": True, "updated_at": ts}},
        return_document=ReturnDocument.AFTER,
    )
