"""Phase 1 acceptance flow, end to end over fixtures:

source -> ingestion job -> fetched data -> normalized product -> staged product
       -> human approval -> published product
"""
from pathlib import Path

import httpx
import pytest

from ingestion import worker
from ingestion.safe_fetch import DomainRateLimiter, SafeFetcher, SourcePolicy
from tests.fixtures.ingestion import scraped_products as fx
from tests.test_ingestion_pipeline import FixtureExtractor
from tests.test_ingestion_review import APPROVE, H, Env

PAGE = (Path(__file__).parent / "fixtures/ingestion/product_page.html").read_text()
BASE = "/products/admin/ingestion"


def fetcher(requests):
    def handler(request):
        requests.append(request)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=PAGE)

    async def dns(_):
        return ["93.184.216.34"]

    return SafeFetcher(SourcePolicy("shop.example", True), resolver=dns, rate_limiter=DomainRateLimiter(0),
                       client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.fixture
def env(monkeypatch):
    return Env(monkeypatch)


def run_worker(env, requests, data=fx.PEARL):
    return env.run(worker.process_next_job(env.db, "qa-worker", fetcher(requests), FixtureExtractor(data)))


def test_source_to_published_product(env):
    requests = []
    # 1. admin queues a product path on the configured source
    job = env.client.post(f"{BASE}/jobs", headers=H, json={"path": "/products/pearl-cashmere-shawl"})
    assert job.status_code == 201 and job.json()["status"] == "queued"

    # 2. worker claims it, fetches (pinned, allowlisted), extracts, normalizes, stages
    done = run_worker(env, requests)
    assert done["status"] == "succeeded"
    assert len(requests) == 1 and requests[0].headers["host"] == "shop.example"
    assert env.client.get(f"{BASE}/jobs/{job.json()['_id']}", headers=H).json()["status"] == "succeeded"

    # 3. the result is staged, hidden, and linked to its job and source
    staged = env.client.get(f"{BASE}/staged", headers=H).json()["items"][0]
    assert staged["status"] == "pending_review" and staged["ingestion_job_id"] == job.json()["_id"]
    assert staged["source_url"] == "https://shop.example/products/pearl-cashmere-shawl"
    assert staged["source_price"] == 189.0 and staged["source_currency"] == "AUD"
    assert staged["product"]["variants"][0]["stock"] == 0 and staged["stock_known"] is False
    assert env.public() == []

    # 4. a human cannot publish without approving
    assert env.act(staged["_id"], "publish").status_code == 409

    # 5. approve with a reviewer-chosen PKR price; still not public
    approved = env.act(staged["_id"], "approve", **APPROVE).json()
    assert approved["status"] == "approved" and env.public() == []

    # 6. explicit publish makes it visible through the existing public API
    assert env.act(staged["_id"], "publish").json()["status"] == "published"
    public = env.public()
    assert [p["slug"] for p in public] == ["pearl-cashmere-shawl"]
    assert public[0]["price"] == 4500 and public[0]["currency"] == "PKR"

    # 7. unpublish hides it again
    env.act(staged["_id"], "unpublish")
    assert env.public() == []


def test_rerunning_the_same_source_product_does_not_duplicate(env):
    requests = []
    first = env.client.post(f"{BASE}/jobs", headers=H, json={"path": "/products/pearl-cashmere-shawl"}).json()
    run_worker(env, requests)
    same = env.client.post(f"{BASE}/jobs", headers=H, json={"path": "/products/pearl-cashmere-shawl"})
    assert same.status_code == 200 and same.json()["_id"] == first["_id"]  # idempotent create
    assert env.client.post(f"{BASE}/jobs/{first['_id']}/rerun", headers=H).json()["status"] == "queued"
    assert run_worker(env, requests)["result"]["outcome"] == "unchanged"
    assert env.client.get(f"{BASE}/staged", headers=H).json()["items"].__len__() == 1


def test_rejected_and_archived_products_never_become_public(env):
    requests = []
    env.client.post(f"{BASE}/jobs", headers=H, json={"path": "/products/pearl-cashmere-shawl"})
    run_worker(env, requests)
    sid = env.client.get(f"{BASE}/staged", headers=H).json()["items"][0]["_id"]
    env.act(sid, "reject", json={"reason": "Not our style"})
    assert env.act(sid, "publish").status_code == 409
    assert env.act(sid, "archive").json()["status"] == "archived"
    assert env.public() == []
    assert env.run(env.db.products.count_documents({})) == 0  # rejection never reaches the catalogue


def test_unsafe_sources_are_refused_end_to_end(env, monkeypatch):
    # Browser-supplied URLs / off-source paths are refused at the API.
    for bad in ("https://evil.example/products/x", "//evil.example/products/x", "/products/../admin"):
        assert env.client.post(f"{BASE}/jobs", headers=H, json={"path": bad}).status_code == 422
    # Even a job that somehow exists never fetches when the source is not authorized.
    env.client.post(f"{BASE}/jobs", headers=H, json={"path": "/products/pearl-cashmere-shawl"})
    called = []
    blocked = SafeFetcher(SourcePolicy("shop.example", False), rate_limiter=DomainRateLimiter(0),
                          client_factory=lambda: (_ for _ in ()).throw(AssertionError("fetched")))
    job = env.run(worker.process_next_job(env.db, "w", blocked, FixtureExtractor(fx.PEARL)))
    assert job["status"] == "failed" and not called
    assert env.run(env.db.staged_products.count_documents({})) == 0
