import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from database.db import ensure_indexes
from ingestion import jobs

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db():
    database = AsyncMongoMockClient().jobs
    await ensure_indexes(database)
    return database


async def new_job(db, path="/products/a", **kw):
    job, _ = await jobs.create_job(db, source_id="s", path=path, now=T0, **kw)
    return job


@pytest.mark.asyncio
async def test_create_is_idempotent(db):
    first, created = await jobs.create_job(db, source_id="s", path="/products/a", now=T0)
    second, created_again = await jobs.create_job(db, source_id="s", path="/products/a", now=T0)
    assert created and not created_again
    assert first["_id"] == second["_id"]
    assert await db.ingestion_jobs.count_documents({}) == 1


@pytest.mark.asyncio
async def test_job_is_claimed_once(db):
    await new_job(db)
    claims = await asyncio.gather(*(jobs.claim_next(db, f"w{i}", T0) for i in range(5)))
    won = [c for c in claims if c]
    assert len(won) == 1
    assert won[0]["status"] == "running" and won[0]["attempts"] == 1


@pytest.mark.asyncio
async def test_future_job_is_not_claimable(db):
    job = await new_job(db)
    await db.ingestion_jobs.update_one({"_id": job["_id"]}, {"$set": {"available_at": T0 + timedelta(hours=1)}})
    assert await jobs.claim_next(db, "w", T0) is None


@pytest.mark.asyncio
async def test_success_releases_lease(db):
    await new_job(db)
    claimed = await jobs.claim_next(db, "w", T0)
    done = await jobs.complete_job(db, claimed["_id"], "w", {"staged": 1}, T0)
    assert done["status"] == "succeeded" and done["lease_owner"] is None


@pytest.mark.asyncio
async def test_wrong_worker_cannot_finish(db):
    await new_job(db)
    claimed = await jobs.claim_next(db, "w1", T0)
    assert await jobs.complete_job(db, claimed["_id"], "w2", {}, T0) is None
    assert await jobs.fail_job(db, claimed["_id"], "w2", "x", retryable=True, now=T0) is None


@pytest.mark.asyncio
async def test_retry_with_backoff_then_terminal_failure(db):
    await new_job(db, max_attempts=2)
    first = await jobs.claim_next(db, "w", T0)
    retrying = await jobs.fail_job(db, first["_id"], "w", "boom", retryable=True, now=T0)
    assert retrying["status"] == "retrying" and retrying["last_error"] == "boom"
    assert await jobs.claim_next(db, "w", T0) is None  # backoff not elapsed
    later = T0 + timedelta(hours=1)
    second = await jobs.claim_next(db, "w", later)
    assert second["attempts"] == 2
    failed = await jobs.fail_job(db, second["_id"], "w", "still broken", retryable=True, now=later)
    assert failed["status"] == "failed" and failed["finished_at"] is not None
    assert await jobs.claim_next(db, "w", later + timedelta(days=1)) is None


@pytest.mark.asyncio
async def test_non_retryable_error_fails_immediately(db):
    await new_job(db)
    claimed = await jobs.claim_next(db, "w", T0)
    failed = await jobs.fail_job(db, claimed["_id"], "w", "invalid source data", retryable=False, now=T0)
    assert failed["status"] == "failed"


@pytest.mark.asyncio
async def test_expired_lease_is_recovered_and_stale_worker_loses(db):
    await new_job(db)
    claimed = await jobs.claim_next(db, "dead", T0)
    assert await jobs.recover_expired_leases(db, T0 + timedelta(seconds=10)) == 0
    after = T0 + timedelta(seconds=jobs.settings.ingestion_job_lease_seconds + 1)
    assert await jobs.recover_expired_leases(db, after) == 1
    job = await db.ingestion_jobs.find_one({"_id": claimed["_id"]})
    assert job["status"] == "retrying"
    assert await jobs.complete_job(db, claimed["_id"], "dead", {}, after) is None
    reclaimed = await jobs.claim_next(db, "alive", after + timedelta(hours=1))
    assert reclaimed["lease_owner"] == "alive"


@pytest.mark.asyncio
async def test_expired_lease_on_last_attempt_fails(db):
    await new_job(db, max_attempts=1)
    await jobs.claim_next(db, "dead", T0)
    await jobs.recover_expired_leases(db, T0 + timedelta(hours=1))
    job = await db.ingestion_jobs.find_one({})
    assert job["status"] == "failed"


@pytest.mark.asyncio
async def test_heartbeat_extends_lease_only_for_owner(db):
    await new_job(db)
    claimed = await jobs.claim_next(db, "w", T0)
    assert await jobs.heartbeat(db, claimed["_id"], "w", T0 + timedelta(seconds=60))
    assert not await jobs.heartbeat(db, claimed["_id"], "other", T0)
    assert await jobs.recover_expired_leases(db, T0 + timedelta(seconds=150)) == 0


@pytest.mark.asyncio
async def test_cancel_queued_and_running(db):
    queued = await new_job(db, path="/products/q")
    cancelled = await jobs.cancel_job(db, queued["_id"], T0)
    assert cancelled["status"] == "cancelled"
    assert await jobs.claim_next(db, "w", T0) is None

    running = await new_job(db, path="/products/r")
    claimed = await jobs.claim_next(db, "w", T0)
    flagged = await jobs.cancel_job(db, claimed["_id"], T0)
    assert flagged["status"] == "running" and flagged["cancel_requested"]
    final = await jobs.complete_job(db, claimed["_id"], "w", {}, T0)
    assert final["status"] == "cancelled"


@pytest.mark.asyncio
async def test_requeue_allows_safe_rerun_of_failed_job(db):
    await new_job(db)
    claimed = await jobs.claim_next(db, "w", T0)
    await jobs.fail_job(db, claimed["_id"], "w", "bad", retryable=False, now=T0)
    again = await jobs.requeue_job(db, claimed["_id"], T0)
    assert again["status"] == "queued" and again["attempts"] == 0
    assert await jobs.requeue_job(db, again["_id"], T0) is None  # not finished
