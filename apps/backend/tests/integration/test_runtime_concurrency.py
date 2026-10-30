"""Concurrency on the cutover runtime path (workers, HTTP review actions, stock, overlapping refreshes), on real PostgreSQL."""
import asyncio
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from ingestion import worker
from ingestion.refresh import run_refresh
from ingestion.safe_fetch import DomainRateLimiter, SafeFetcher, SourcePolicy
from tests.fixtures.ingestion import scraped_products as fx
from tests.integration.api_support import H
from tests.integration.test_api_review import APPROVE, Env
from tests.refresh_support import OLD, ROOT, SOURCES, site, urlset, product_page  # noqa: F401  (site is a fixture)

POLICY = SourcePolicy("shop.example", True)
BARE_PAGE = "<html><head><title>x</title></head><body>x</body></html>"        # no source product id: dedupe is by URL


class PerUrlExtractor:
    async def extract(self, *, source_url, sanitized_html, text, raw_html=""):
        handle = source_url.rsplit("/", 1)[1]
        return {**fx.PEARL, "url": source_url, "title": f"Shawl {handle}"}


def fetcher():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=BARE_PAGE)

    async def dns(_):
        return ["93.184.216.34"]

    return SafeFetcher(POLICY, resolver=dns, rate_limiter=DomainRateLimiter(0),
                       client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.asyncio
async def test_concurrent_workers_process_every_job_exactly_once(db):
    for n in range(10):
        await db.create_job(f"/products/p-{n}")
    shared, extractor = fetcher(), PerUrlExtractor()

    async def run_worker(name):
        done = []
        while True:
            job = await worker.process_next_job(db.sessions, name, shared, extractor)
            if job is None:
                return done
            done.append(job.id)

    results = await asyncio.gather(*(run_worker(f"w{i}") for i in range(5)))
    handled = [j for r in results for j in r]
    assert len(handled) == len(set(handled)) == 10                              # no job ran twice
    jobs = await db.jobs()
    assert {(j.status, j.attempts) for j in jobs} == {("succeeded", 1)}
    assert await db.count("staged_products") == 10 and len({s.dedupe_key for s in await db.staged()}) == 10


@pytest.mark.asyncio
async def test_two_jobs_for_the_same_product_running_at_once_stage_it_once(db):
    for key in ("a", "b", "c", "d"):
        await db.create_job("/products/same", idempotency_key=key)
    shared, extractor = fetcher(), PerUrlExtractor()

    async def run_worker(name):
        while await worker.process_next_job(db.sessions, name, shared, extractor):
            pass

    await asyncio.gather(*(run_worker(f"w{i}") for i in range(4)))
    assert await db.count("staged_products") == 1
    outcomes = sorted(j.result["outcome"] for j in await db.jobs())
    assert outcomes == ["created", "unchanged", "unchanged", "unchanged"]
    assert len((await db.staged_one()).audit) == 1                              # one "staged" entry, not four


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    return Env(migrated_url, monkeypatch)


def parallel(calls):
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return [f.result() for f in [pool.submit(call) for call in calls]]


def test_simultaneous_http_approvals_create_exactly_one_draft(env):
    sid = env.stage()
    responses = parallel([lambda: env.act(sid, "approve", **APPROVE) for _ in range(6)])
    assert sorted(r.status_code for r in responses) == [200] + [409] * 5
    assert env.sql("select count(*), count(*) filter (where status = 'draft') from products")[0] == (1, 1)
    assert env.sql("select count(*) from variants")[0][0] == 1
    assert [a["action"] for a in env.client.get(f"/products/admin/ingestion/staged/{sid}", headers=H).json()["audit"]] == ["staged", "approve"]


def test_simultaneous_approve_and_reject_leave_one_consistent_outcome(env):
    sid = env.stage()
    responses = parallel([lambda: env.act(sid, "approve", **APPROVE), lambda: env.act(sid, "reject", json={"reason": "Not suitable"})])
    assert sorted(r.status_code for r in responses) == [200, 409]
    status = env.client.get(f"/products/admin/ingestion/staged/{sid}", headers=H).json()["status"]
    assert status in {"approved", "rejected"}
    assert env.sql("select count(*) from products")[0][0] == (1 if status == "approved" else 0)


def test_interleaved_publish_and_unpublish_never_split_the_staged_and_product_state(env):
    sid = env.stage()
    env.act(sid, "approve", **APPROVE)
    env.act(sid, "publish")
    parallel([(lambda action=action: env.act(sid, action)) for action in ("unpublish", "publish", "unpublish", "publish", "archive")])
    staged = env.client.get(f"/products/admin/ingestion/staged/{sid}", headers=H).json()
    product = env.client.get(f"/products/admin/{staged['product_id']}", headers=H).json()
    expected = {"published": "active", "unpublished": "draft", "archived": "archived"}[staged["status"]]
    assert product["status"] == expected, (staged["status"], product["status"])
    assert (product["status"] == "active") == (staged["status"] == "published")
    actions = [a["action"] for a in staged["audit"]]
    assert actions[:3] == ["staged", "approve", "publish"]                       # the trail only ever grows from the start


def test_simultaneous_stock_updates_all_apply_without_corruption(env):
    created = env.client.post("/products/admin/", headers=H, json={
        "name": "Stock", "slug": "stock", "cover_image_url": "https://x/a.jpg", "status": "active",
        "variants": [{"name": "v", "image_url": "https://x/a.jpg", "price": 1, "stock": 1}]}).json()
    variant_id = created["variants"][0]["_id"]
    responses = parallel([(lambda n=n: env.client.patch(f"/products/admin/{created['_id']}/stock", headers=H,
                                                        json={"variant_id": variant_id, "stock": n})) for n in range(10, 20)])
    assert [r.status_code for r in responses] == [200] * 10
    row = env.sql("select (select stock from variants limit 1), (select stock_status from variants limit 1), revision from products")[0]
    assert row[0] in range(10, 20) and row[1] == "In stock" and row[2] == 11


@pytest.mark.asyncio
async def test_two_overlapping_refresh_runs_never_duplicate_jobs_or_staged_products(db, site):
    site.xml(ROOT, urlset(("https://shop.example/products/a", OLD), ("https://shop.example/products/b", OLD)))

    async def run():
        return await run_refresh(db.sessions, sources=SOURCES, fetcher_factory=lambda p: site.factory(p))

    await asyncio.gather(run(), run())
    assert await db.count("ingestion_jobs") == 2 and await db.count("staged_products") == 2
    assert {j.attempts for j in await db.jobs()} == {1}                         # each product was fetched and staged once
    assert {s.status for s in await db.staged()} == {"pending_review"}
