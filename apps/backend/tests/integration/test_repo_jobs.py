import asyncio
import uuid
from datetime import timedelta

import pytest

from configuration.config import settings
from repositories import jobs as repo
from tests.integration.repo_helpers import NOW, count, run_repo, tx

LEASE = timedelta(seconds=settings.ingestion_job_lease_seconds)


async def enqueue(sessions, path="/products/a", **over):
    async with tx(sessions) as s:
        job, created = await repo.create_job(s, source_id="primary", path=path, now=over.pop("now", NOW), **over)
    return job, created


async def claim(sessions, worker="w1", now=NOW, **kwargs):
    async with tx(sessions) as s:
        return await repo.claim_next(s, worker, now=now, **kwargs)


# ---- enqueue with idempotency -----------------------------------------------------------------
def test_enqueue_creates_a_queued_job_with_defaults(pg_engine_factory):
    async def scenario(sessions):
        job, created = await enqueue(sessions)
        return (created, job.status, job.attempts, job.max_attempts, job.cancel_requested, job.lease_owner,
                job.available_at, isinstance(job.id, uuid.UUID), job.idempotency_key == repo.idempotency_key_for("primary", "/products/a"))

    assert run_repo(pg_engine_factory, scenario) == (True, "queued", 0, settings.ingestion_job_max_attempts, False, None, NOW, True, True)


def test_enqueue_is_idempotent_per_source_and_path(pg_engine_factory):
    async def scenario(sessions):
        first, c1 = await enqueue(sessions)
        again, c2 = await enqueue(sessions)
        other, c3 = await enqueue(sessions, "/products/b")
        explicit, c4 = await enqueue(sessions, "/products/a", idempotency_key="custom-key", max_attempts=5)
        return (c1, c2, c3, c4, again.id == first.id, other.id != first.id, explicit.max_attempts,
                await count(sessions, "ingestion_jobs"))

    assert run_repo(pg_engine_factory, scenario) == (True, False, True, True, True, True, 5, 3)


def test_concurrent_enqueues_of_the_same_work_create_one_job(pg_engine_factory):
    async def scenario(sessions):
        results = await asyncio.gather(*(enqueue(sessions) for _ in range(8)))
        return sorted(created for _, created in results), len({job.id for job, _ in results}), await count(sessions, "ingestion_jobs")

    assert run_repo(pg_engine_factory, scenario) == ([False] * 7 + [True], 1, 1)


# ---- claim with SELECT ... FOR UPDATE SKIP LOCKED --------------------------------------------
def test_claim_takes_the_oldest_due_job_and_starts_its_lease(pg_engine_factory):
    async def scenario(sessions):
        await enqueue(sessions, "/late", now=NOW - timedelta(minutes=1))
        await enqueue(sessions, "/early", now=NOW - timedelta(minutes=9))
        job = await claim(sessions, "worker-1")
        return (job.path, job.status, job.lease_owner, job.attempts, job.lease_expires_at - NOW, job.heartbeat_at,
                job.started_at)

    assert run_repo(pg_engine_factory, scenario) == ("/early", "running", "worker-1", 1, LEASE, NOW, NOW)


def test_claim_skips_future_cancelled_running_and_finished_jobs(pg_engine_factory):
    async def scenario(sessions):
        await enqueue(sessions, "/future", now=NOW + timedelta(hours=1))
        cancelled, _ = await enqueue(sessions, "/cancelled")
        async with tx(sessions) as s:
            await repo.cancel_job(s, cancelled.id, now=NOW)
        taken, _ = await enqueue(sessions, "/taken")
        assert (await claim(sessions, "w1")).id == taken.id            # the only due job
        first = await claim(sessions, "w2")                             # nothing left: running jobs are not re-claimed
        later = await claim(sessions, "w2", now=NOW + timedelta(hours=2))
        return first, later.path

    assert run_repo(pg_engine_factory, scenario) == (None, "/future")


def test_claim_can_be_limited_to_a_batch(pg_engine_factory):
    async def scenario(sessions):
        wanted, _ = await enqueue(sessions, "/wanted", now=NOW - timedelta(minutes=1))
        await enqueue(sessions, "/older-but-not-mine", now=NOW - timedelta(minutes=9))
        mine = await claim(sessions, "w1", only_ids=[wanted.id])
        nothing = await claim(sessions, "w1", only_ids=[uuid.uuid4()])
        return mine.path, nothing

    assert run_repo(pg_engine_factory, scenario) == ("/wanted", None)


def test_concurrent_workers_never_claim_the_same_job(pg_engine_factory):
    async def scenario(sessions):
        for n in range(12):
            await enqueue(sessions, f"/p/{n}")

        async def worker(name):
            mine = []
            while True:
                async with tx(sessions) as s:                           # claim, then COMMIT to release the row lock
                    job = await repo.claim_next(s, name, now=NOW)
                if job is None:
                    return mine
                mine.append(job.id)
                await asyncio.sleep(0)                                  # let the other workers interleave

        results = await asyncio.gather(*(worker(f"w{i}") for i in range(6)))
        flat = [i for r in results for i in r]
        return len(flat), len(set(flat)), await count(sessions, "ingestion_jobs", "status = 'running' AND attempts = 1")

    assert run_repo(pg_engine_factory, scenario) == (12, 12, 12)       # every job claimed exactly once


def test_a_claim_is_not_durable_until_the_caller_commits(pg_engine_factory):
    async def scenario(sessions):
        job, _ = await enqueue(sessions)
        async with sessions() as s:
            claimed = await repo.claim_next(s, "w1", now=NOW)
            assert claimed.status == "running"
            await s.rollback()                                           # e.g. the worker crashed before committing
        async with sessions() as s:
            return (await repo.get_job(s, job.id)).status, (await repo.get_job(s, job.id)).attempts

    assert run_repo(pg_engine_factory, scenario) == ("queued", 0)


def test_uncommitted_claims_hold_back_other_workers_without_blocking_them(pg_engine_factory):
    async def scenario(sessions):
        one, _ = await enqueue(sessions, "/one", now=NOW - timedelta(minutes=2))
        two, _ = await enqueue(sessions, "/two", now=NOW - timedelta(minutes=1))
        async with sessions() as holder, sessions() as other:
            async with holder.begin():
                first = await repo.claim_next(holder, "holder", now=NOW)      # still uncommitted: row-locked
                async with other.begin():
                    second = await repo.claim_next(other, "other", now=NOW)   # SKIP LOCKED: gets the next job, no waiting
                    third = await repo.claim_next(other, "other", now=NOW)
        return first.path, second.path, third

    assert run_repo(pg_engine_factory, scenario) == ("/one", "/two", None)


# ---- heartbeat ---------------------------------------------------------------------------------
def test_heartbeat_extends_the_lease_for_its_owner_only(pg_engine_factory):
    async def scenario(sessions):
        job, _ = await enqueue(sessions)
        await claim(sessions, "w1")
        later = NOW + timedelta(seconds=60)
        async with tx(sessions) as s:
            owner = await repo.heartbeat(s, job.id, "w1", now=later)
            stranger = await repo.heartbeat(s, job.id, "w2", now=later)
            missing = await repo.heartbeat(s, uuid.uuid4(), "w1", now=later)
        async with sessions() as s:
            row = await repo.get_job(s, job.id)
        return owner, stranger, missing, row.heartbeat_at, row.lease_expires_at - later

    assert run_repo(pg_engine_factory, scenario) == (True, False, False, NOW + timedelta(seconds=60), LEASE)


def test_heartbeat_is_refused_once_the_job_is_no_longer_running(pg_engine_factory):
    async def scenario(sessions):
        job, _ = await enqueue(sessions)
        await claim(sessions, "w1")
        async with tx(sessions) as s:
            await repo.complete_job(s, job.id, "w1", {"ok": True}, now=NOW)
            return await repo.heartbeat(s, job.id, "w1", now=NOW)

    assert run_repo(pg_engine_factory, scenario) is False


# ---- complete / fail / retry / backoff --------------------------------------------------------
def test_complete_records_the_result_and_releases_the_lease(pg_engine_factory):
    async def scenario(sessions):
        job, _ = await enqueue(sessions)
        await claim(sessions, "w1")
        async with tx(sessions) as s:
            done = await repo.complete_job(s, job.id, "w1", {"created": 1}, now=NOW + timedelta(seconds=5))
        return (done.status, done.result, done.lease_owner, done.lease_expires_at, done.last_error,
                done.finished_at - NOW)

    assert run_repo(pg_engine_factory, scenario) == ("succeeded", {"created": 1}, None, None, None, timedelta(seconds=5))


def test_a_worker_that_lost_its_lease_cannot_overwrite_the_outcome(pg_engine_factory):
    async def scenario(sessions):
        job, _ = await enqueue(sessions)
        await claim(sessions, "w1")
        async with tx(sessions) as s:                                     # w1 stalls; the lease is recovered; w2 takes over
            await repo.recover_expired_leases(s, now=NOW + LEASE + timedelta(seconds=1))
        await claim(sessions, "w2", now=NOW + LEASE + timedelta(hours=1))
        async with tx(sessions) as s:
            stale_complete = await repo.complete_job(s, job.id, "w1", {"late": True}, now=NOW)
            stale_fail = await repo.fail_job(s, job.id, "w1", "late failure", retryable=False, now=NOW)
            stale_beat = await repo.heartbeat(s, job.id, "w1", now=NOW)
        async with sessions() as s:
            row = await repo.get_job(s, job.id)
        return stale_complete, stale_fail, stale_beat, row.status, row.lease_owner, row.result

    assert run_repo(pg_engine_factory, scenario) == (None, None, False, "running", "w2", None)


def test_retryable_failure_backs_off_exponentially_until_attempts_run_out(pg_engine_factory):
    async def scenario(sessions):
        job, _ = await enqueue(sessions, max_attempts=3)
        timeline, clock = [], NOW
        for attempt in (1, 2, 3):
            claimed = await claim(sessions, "w1", now=clock)
            assert claimed.attempts == attempt
            async with tx(sessions) as s:
                failed = await repo.fail_job(s, job.id, "w1", "temporary", retryable=True, now=clock)
            timeline.append((failed.status, failed.available_at - clock if failed.status == "retrying" else None,
                             failed.lease_owner, failed.finished_at is not None))
            if failed.status == "retrying":
                too_early = await claim(sessions, "w1", now=clock + (failed.available_at - clock) - timedelta(seconds=1))
                assert too_early is None                                   # not claimable before the backoff elapses
                clock = failed.available_at
        return timeline

    base = timedelta(seconds=settings.ingestion_job_backoff_seconds)
    assert run_repo(pg_engine_factory, scenario) == [
        ("retrying", base, None, False), ("retrying", base * 2, None, False), ("failed", None, None, True)]


def test_non_retryable_failure_is_terminal_and_the_error_is_clipped(pg_engine_factory):
    async def scenario(sessions):
        job, _ = await enqueue(sessions)
        await claim(sessions, "w1")
        async with tx(sessions) as s:
            failed = await repo.fail_job(s, job.id, "w1", "x" * 900, retryable=False, now=NOW)
        return failed.status, len(failed.last_error), failed.finished_at, failed.lease_owner

    assert run_repo(pg_engine_factory, scenario) == ("failed", repo.MAX_ERROR_LENGTH, NOW, None)


def test_attempts_never_exceed_the_maximum(pg_engine_factory):
    async def scenario(sessions):
        job, _ = await enqueue(sessions, max_attempts=1)
        await claim(sessions, "w1")
        async with tx(sessions) as s:
            failed = await repo.fail_job(s, job.id, "w1", "temporary", retryable=True, now=NOW)   # retryable but out of attempts
        again = await claim(sessions, "w1", now=NOW + timedelta(days=1))
        return failed.status, failed.attempts, again

    assert run_repo(pg_engine_factory, scenario) == ("failed", 1, None)


# ---- lease recovery ----------------------------------------------------------------------------
def test_recovery_requeues_abandoned_jobs_and_fails_exhausted_ones(pg_engine_factory):
    async def scenario(sessions):
        fresh, _ = await enqueue(sessions, "/fresh", max_attempts=3)
        spent, _ = await enqueue(sessions, "/spent", max_attempts=1)
        cancelled, _ = await enqueue(sessions, "/cancelled", max_attempts=3)
        healthy, _ = await enqueue(sessions, "/healthy", max_attempts=3)
        for path in ("/fresh", "/spent", "/cancelled"):
            async with tx(sessions) as s:
                job = await repo.claim_next(s, "dead-worker", now=NOW, only_ids=[{"/fresh": fresh, "/spent": spent, "/cancelled": cancelled}[path].id])
        async with tx(sessions) as s:
            await repo.cancel_job(s, cancelled.id, now=NOW)               # asked to stop while its worker was dying
        healthy_job = await claim(sessions, "alive", now=NOW + LEASE)     # claimed later: its lease is still valid
        after_expiry = NOW + LEASE + timedelta(seconds=1)
        async with tx(sessions) as s:
            recovered = await repo.recover_expired_leases(s, now=after_expiry)
        async with sessions() as s:
            rows = {j.path: j for j in [await repo.get_job(s, x.id) for x in (fresh, spent, cancelled, healthy)]}
        base = timedelta(seconds=settings.ingestion_job_backoff_seconds)
        return (recovered, rows["/fresh"].status, rows["/fresh"].available_at - after_expiry, rows["/fresh"].lease_owner,
                rows["/fresh"].last_error, rows["/spent"].status, rows["/spent"].last_error, rows["/cancelled"].status,
                rows["/healthy"].status, rows["/healthy"].lease_owner, base > timedelta(0))

    assert run_repo(pg_engine_factory, scenario) == (
        3, "retrying", timedelta(seconds=settings.ingestion_job_backoff_seconds), None,
        "Lease expired; worker presumed stopped", "failed", "Lease expired after final attempt", "cancelled",
        "running", "alive", True)


def test_concurrent_recoverers_do_not_double_handle_a_job(pg_engine_factory):
    async def scenario(sessions):
        for n in range(8):
            job, _ = await enqueue(sessions, f"/p/{n}", max_attempts=5)
        for _ in range(8):
            await claim(sessions, "dead", now=NOW)
        late = NOW + LEASE + timedelta(seconds=1)

        async def recover():
            async with tx(sessions) as s:
                return await repo.recover_expired_leases(s, now=late)

        totals = await asyncio.gather(*(recover() for _ in range(4)))
        return sum(totals), await count(sessions, "ingestion_jobs", "status = 'retrying'")

    assert run_repo(pg_engine_factory, scenario) == (8, 8)


# ---- cancel / requeue --------------------------------------------------------------------------
def test_cancel_stops_queued_jobs_immediately_and_running_jobs_at_the_next_checkpoint(pg_engine_factory):
    async def scenario(sessions):
        queued, _ = await enqueue(sessions, "/queued")
        running, _ = await enqueue(sessions, "/running")
        await claim(sessions, "w1", only_ids=[running.id])
        async with tx(sessions) as s:
            q = await repo.cancel_job(s, queued.id, now=NOW)
            r = await repo.cancel_job(s, running.id, now=NOW)
        queued_state = (q.status, q.cancel_requested, q.finished_at)
        running_state = (r.status, r.cancel_requested, r.lease_owner)          # still running until the worker checks in
        async with tx(sessions) as s:
            done = await repo.complete_job(s, running.id, "w1", {"partial": True}, now=NOW)   # completion honours the cancellation
        async with tx(sessions) as s:
            repeat = await repo.cancel_job(s, queued.id, now=NOW)                # already finished
            unknown = await repo.cancel_job(s, uuid.uuid4(), now=NOW)
        return queued_state, running_state, (done.status, done.result, done.lease_owner), repeat, unknown

    assert run_repo(pg_engine_factory, scenario) == (
        ("cancelled", True, NOW), ("running", True, "w1"), ("cancelled", None, None), None, None)


def test_a_cancelled_running_job_that_fails_is_cancelled_not_retried(pg_engine_factory):
    async def scenario(sessions):
        job, _ = await enqueue(sessions)
        await claim(sessions, "w1")
        async with tx(sessions) as s:
            await repo.cancel_job(s, job.id, now=NOW)
            failed = await repo.fail_job(s, job.id, "w1", "boom", retryable=True, now=NOW)
        return failed.status, failed.finished_at

    assert run_repo(pg_engine_factory, scenario) == ("cancelled", NOW)


def test_only_finished_jobs_can_be_requeued_and_requeue_resets_them(pg_engine_factory):
    async def scenario(sessions):
        job, _ = await enqueue(sessions)
        async with tx(sessions) as s:
            not_finished = await repo.requeue_job(s, job.id, now=NOW)
        await claim(sessions, "w1")
        async with tx(sessions) as s:
            await repo.fail_job(s, job.id, "w1", "bad", retryable=False, now=NOW)
        later = NOW + timedelta(hours=1)
        async with tx(sessions) as s:
            again = await repo.requeue_job(s, job.id, now=later)
            unknown = await repo.requeue_job(s, uuid.uuid4(), now=later)
        reclaimed = await claim(sessions, "w2", now=later)
        return (not_finished, again.status, again.attempts, again.last_error, again.finished_at, again.cancel_requested,
                unknown, reclaimed.id == job.id, reclaimed.attempts)

    assert run_repo(pg_engine_factory, scenario) == (None, "queued", 0, None, None, False, None, True, 1)


# ---- listing -----------------------------------------------------------------------------------
def test_list_jobs_is_newest_first_and_limited(pg_engine_factory):
    async def scenario(sessions):
        for n in range(5):
            async with tx(sessions) as s:
                await repo.create_job(s, source_id="primary", path=f"/p/{n}", now=NOW + timedelta(seconds=n))
        async with sessions() as s:
            return [j.path for j in await repo.list_jobs(s, 3)]

    # created_at defaults to the transaction clock, so order follows insertion across transactions
    assert run_repo(pg_engine_factory, scenario) == ["/p/4", "/p/3", "/p/2"]


def test_one_job_and_five_simultaneous_claimers_has_exactly_one_winner(pg_engine_factory):
    async def scenario(sessions):
        await enqueue(sessions)

        async def attempt(name):
            async with tx(sessions) as s:
                return await repo.claim_next(s, name, now=NOW)

        claims = await asyncio.gather(*(attempt(f"w{i}") for i in range(5)))
        won = [c for c in claims if c]
        return len(won), won[0].status, won[0].attempts

    assert run_repo(pg_engine_factory, scenario) == (1, "running", 1)


def test_the_retryability_of_the_last_failure_is_recorded(pg_engine_factory):
    async def scenario(sessions):
        seen = []
        for retryable in (True, False):
            job, _ = await enqueue(sessions, f"/p/{retryable}", max_attempts=3)
            await claim(sessions, "w1", only_ids=[job.id])
            async with tx(sessions) as s:
                failed = await repo.fail_job(s, job.id, "w1", "boom", retryable=retryable, now=NOW)
            seen.append((failed.status, failed.last_error_retryable))
        fresh, _ = await enqueue(sessions, "/p/fresh")
        return seen, fresh.last_error_retryable

    assert run_repo(pg_engine_factory, scenario) == ([("retrying", True), ("failed", False)], None)
