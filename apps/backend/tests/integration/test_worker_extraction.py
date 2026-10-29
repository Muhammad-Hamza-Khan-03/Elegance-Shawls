"""The deterministic extractor through the real worker, on PostgreSQL."""
from pathlib import Path

import httpx
import pytest

from ingestion import worker
from ingestion.extractors import ShopifyHtmlExtractor
from ingestion.safe_fetch import DomainRateLimiter, SafeFetcher, SourcePolicy

FIX = Path(__file__).resolve().parents[1] / "fixtures/ingestion/shopify"
POLICY = SourcePolicy("shop.example", True, frozenset({"cdn.shopify.com"}), frozenset({"www.shop.example"}))


def load(name):
    return (FIX / name).read_text()


def fetcher_for(html):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    async def dns(_):
        return ["93.184.216.34"]

    return SafeFetcher(POLICY, resolver=dns, rate_limiter=DomainRateLimiter(0),
                       client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.asyncio
async def test_worker_stages_a_product_using_the_deterministic_extractor(db):
    await db.create_job("/products/heritage-wool-shawl")
    job = await worker.process_next_job(db.sessions, "w", fetcher_for(load("jsonld_full.html")), ShopifyHtmlExtractor())
    assert job.status == "succeeded"
    staged = await db.staged_one()
    assert staged.status == "pending_review" and staged.source_product_id == "8800112233"
    assert float(staged.source_price) == 1089.5 and staged.source_currency == "AUD"
    assert staged.product["name"] == "Heritage Wool Shawl" and staged.product["material"] == "100% Merino Wool"
    assert staged.product["cover_image_url"].startswith("https://cdn.shopify.com/")
    assert "price" in staged.missing_fields and "stock" in staged.missing_fields
    assert await db.count("products") == 0


@pytest.mark.asyncio
async def test_worker_strips_hostile_markup_and_offsite_images(db):
    await db.create_job("/products/evil-shawl")
    job = await worker.process_next_job(db.sessions, "w", fetcher_for(load("hostile.html")), ShopifyHtmlExtractor())
    assert job.status == "succeeded"
    staged = await db.staged_one()
    assert "<" not in staged.product["name"] and "<" not in staged.product["main_description"]
    assert staged.product["images"] == ["https://cdn.shopify.com/ok.jpg"]  # javascript: and evil.example dropped
    assert staged.status == "pending_review"


@pytest.mark.asyncio
async def test_worker_fails_terminally_on_unextractable_page(db):
    await db.create_job("/products/nothing")
    job = await worker.process_next_job(db.sessions, "w", fetcher_for(load("empty.html")), ShopifyHtmlExtractor())
    assert job.status == "failed" and job.attempts == 1 and "title" in job.last_error
    assert job.last_error_retryable is False
    assert await db.count("staged_products") == 0


@pytest.mark.asyncio
async def test_apex_to_www_redirect_stages_under_the_canonical_host_once(db):
    page = load("jsonld_full.html")

    def handler(request):
        if request.headers["host"] == "shop.example":
            return httpx.Response(301, headers={"location": "https://www.shop.example/products/heritage-wool-shawl"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=page)

    async def dns(_):
        return ["93.184.216.34"]

    fetcher = SafeFetcher(POLICY, resolver=dns, rate_limiter=DomainRateLimiter(0),
                          client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await db.create_job("/products/heritage-wool-shawl", idempotency_key="1")
    assert (await worker.process_next_job(db.sessions, "w", fetcher, ShopifyHtmlExtractor())).status == "succeeded"
    staged = await db.staged_one()
    assert staged.source_url == "https://shop.example/products/heritage-wool-shawl"
    await db.create_job("/products/heritage-wool-shawl", idempotency_key="2")
    assert (await worker.process_next_job(db.sessions, "w", fetcher, ShopifyHtmlExtractor())).result["outcome"] == "unchanged"
    assert await db.count("staged_products") == 1


@pytest.mark.asyncio
async def test_homepage_redirect_fails_without_staging_a_product(db):
    def handler(request):
        if request.url.path == "/products/heritage-wool-shawl":
            return httpx.Response(301, headers={"location": "https://shop.example/"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=load("jsonld_full.html"))

    async def dns(_):
        return ["93.184.216.34"]

    fetcher = SafeFetcher(
        POLICY,
        resolver=dns,
        rate_limiter=DomainRateLimiter(0),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    await db.create_job("/products/heritage-wool-shawl", idempotency_key="homepage")
    job = await worker.process_next_job(db.sessions, "w", fetcher, ShopifyHtmlExtractor())
    assert job.status == "failed" and job.attempts == 1 and job.last_error_retryable is False
    assert await db.count("staged_products") == 0
