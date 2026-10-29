"""End-to-end ingestion (fetch -> extract -> normalize -> stage) through the worker, on PostgreSQL."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from ingestion import worker
from ingestion.safe_fetch import DomainRateLimiter, SafeFetcher, SourcePolicy
from repositories import jobs as jobs_repo
from tests.fixtures.ingestion import scraped_products as fx

PAGE = (Path(__file__).resolve().parents[1] / "fixtures/ingestion/product_page.html").read_text()
POLICY = SourcePolicy("shop.example", True)
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FixtureExtractor:
    def __init__(self, data):
        self.data, self.calls = data, 0

    async def extract(self, *, source_url, sanitized_html, text, raw_html=""):
        self.calls += 1
        return self.data


def make_fetcher(status=200, text=PAGE):
    def handler(request):
        return httpx.Response(status, headers={"content-type": "text/html"}, text=text)

    async def dns(_):
        return ["93.184.216.34"]

    return SafeFetcher(POLICY, resolver=dns, rate_limiter=DomainRateLimiter(0),
                       client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def enqueue(db, path="/products/pearl-cashmere-shawl", **kw):
    job, _ = await db.create_job(path, **kw)
    return job


async def run(db, data=fx.PEARL, fetcher=None, extractor=None):
    return await worker.process_next_job(db.sessions, "w1", fetcher or make_fetcher(), extractor or FixtureExtractor(data))


@pytest.mark.asyncio
async def test_successful_ingestion_stages_pending_review(db):
    await enqueue(db)
    job = await run(db)
    assert job.status == "succeeded" and job.result["outcome"] == "created"
    staged = await db.staged_one()
    assert staged.status == "pending_review"
    assert staged.source_product_id == "7712345678"
    assert staged.dedupe_key == "id:7712345678"
    assert staged.ingestion_job_id == job.id
    assert staged.source_url == "https://shop.example/products/pearl-cashmere-shawl"
    assert staged.product_id is None
    assert await db.count("products") == 0  # nothing reaches the catalogue


@pytest.mark.asyncio
async def test_page_images_are_merged_into_staged_product(db):
    await enqueue(db)
    await run(db)
    images = (await db.staged_one()).product["images"]
    assert "https://shop.example/cdn/shop/files/pearl_detail_1800x.jpg" in images


@pytest.mark.asyncio
async def test_rerunning_same_job_does_not_duplicate(db):
    job = await enqueue(db)
    await run(db)
    async with db.sessions() as session, session.begin():
        await jobs_repo.requeue_job(session, job.id)
    again = await run(db)
    assert again.result["outcome"] == "unchanged"
    assert await db.count("staged_products") == 1


@pytest.mark.asyncio
async def test_same_product_under_a_new_job_is_not_duplicated(db):
    await enqueue(db, idempotency_key="one")
    await run(db)
    await enqueue(db, idempotency_key="two")
    await run(db)
    assert await db.count("staged_products") == 1


@pytest.mark.asyncio
async def test_changed_source_updates_pending_but_not_reviewed_products(db):
    await enqueue(db, idempotency_key="1")
    await run(db)
    await enqueue(db, idempotency_key="2")
    changed = await run(db, {**fx.PEARL, "price": 250.0})
    assert changed.result["outcome"] == "updated"
    assert float((await db.staged_one()).source_price) == 250.0

    # reviewed = approved through the repository, so the row satisfies the approval constraints
    async with db.sessions() as session, session.begin():
        from repositories import staged as staged_repo
        await staged_repo.approve(session, (await db.staged_one()).id, price=4500, stock=1)
    await enqueue(db, idempotency_key="3")
    flagged = await run(db, {**fx.PEARL, "price": 300.0})
    assert flagged.result["outcome"] == "source_changed"
    row = await db.staged_one()
    assert float(row.source_price) == 250.0 and row.status == "approved" and row.latest_source_hash


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [fx.INVALID_NO_TITLE, fx.INVALID_CATEGORY, None])
async def test_invalid_source_data_fails_terminally_and_stages_nothing(db, data):
    await enqueue(db)
    job = await run(db, data)
    assert job.status == "failed" and job.attempts == 1 and job.last_error_retryable is False
    assert await db.count("staged_products") == 0


@pytest.mark.asyncio
async def test_transient_fetch_failure_retries_then_fails_terminally(db):
    await enqueue(db, max_attempts=2)
    first = await run(db, fetcher=make_fetcher(503, ""))
    assert first.status == "retrying" and first.last_error_retryable is True
    assert await worker.process_next_job(db.sessions, "w", make_fetcher(503, ""), FixtureExtractor(fx.PEARL)) is None  # backoff
    await db.set_jobs({"available_at": NOW})
    last = await run(db, fetcher=make_fetcher(503, ""))
    assert last.status == "failed" and "503" in last.last_error and last.last_error_retryable is True


@pytest.mark.asyncio
async def test_timeout_is_retried(db):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    async def dns(_):
        return ["93.184.216.34"]

    fetcher = SafeFetcher(POLICY, resolver=dns, rate_limiter=DomainRateLimiter(0),
                          client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await enqueue(db)
    job = await run(db, fetcher=fetcher)
    assert job.status == "retrying" and "timed out" in job.last_error


@pytest.mark.asyncio
async def test_unauthorized_source_never_fetches(db):
    def handler(request):
        raise AssertionError("must not fetch")

    fetcher = SafeFetcher(SourcePolicy("shop.example", False), rate_limiter=DomainRateLimiter(0),
                          client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await enqueue(db)
    job = await run(db, fetcher=fetcher)
    assert job.status == "failed" and "authorized" in job.last_error


@pytest.mark.asyncio
async def test_crashed_worker_job_is_recovered_and_completed(db):
    long_ago = NOW - timedelta(hours=3)
    await enqueue(db, now=long_ago)
    async with db.sessions() as session, session.begin():
        assert await jobs_repo.claim_next(session, "dead", long_ago)  # worker dies holding the lease
    assert await run(db) is None  # recovery requeues with backoff; not claimable yet
    assert (await db.job()).status == "retrying"
    await db.set_jobs({"available_at": NOW})
    job = await run(db)
    assert job.status == "succeeded" and job.attempts == 2


@pytest.mark.asyncio
async def test_a_worker_never_holds_a_transaction_while_fetching(db):
    """Claim commits before the HTTP fetch: another connection sees the job as running while the fetch is in flight."""
    seen = {}

    class Probe(FixtureExtractor):
        async def extract(self, **kwargs):
            seen["status"] = (await db.job()).status
            return await super().extract(**kwargs)

    await enqueue(db)
    await run(db, extractor=Probe(fx.PEARL))
    assert seen["status"] == "running"


@pytest.mark.asyncio
async def test_runtime_error_in_a_job_is_retryable_and_hides_the_detail(db):
    class Boom(FixtureExtractor):
        async def extract(self, **kwargs):
            raise RuntimeError("secret-connection-detail")

    await enqueue(db)
    job = await run(db, extractor=Boom(fx.PEARL))
    assert job.status == "retrying" and job.last_error == "Unexpected internal error" and job.last_error_retryable is True
