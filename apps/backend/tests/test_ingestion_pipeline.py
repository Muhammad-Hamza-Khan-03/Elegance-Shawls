from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from database.db import ensure_indexes
from ingestion import jobs, worker
from ingestion.normalize import InvalidSourceData, normalize, slugify, source_url_for_path
from ingestion.quill_scraper import ProductShawl
from ingestion.safe_fetch import DomainRateLimiter, SafeFetcher, SourcePolicy, UnsafeURL
from tests.fixtures.ingestion import scraped_products as fx

PAGE = (Path(__file__).parent / "fixtures/ingestion/product_page.html").read_text()
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


@pytest_asyncio.fixture
async def db():
    database = AsyncMongoMockClient().pipe
    await ensure_indexes(database)
    return database


async def enqueue(db, path="/products/pearl-cashmere-shawl", **kw):
    job, _ = await jobs.create_job(db, source_id="primary", path=path, **kw)
    return job


async def run(db, data=fx.PEARL, fetcher=None, extractor=None):
    return await worker.process_next_job(db, "w1", fetcher or make_fetcher(), extractor or FixtureExtractor(data))


# ---- normalization -------------------------------------------------------

def norm(data):
    return normalize(ProductShawl.model_validate(data), policy=POLICY, source_product_id="77", fetched_at=NOW)


def test_valid_output_normalizes_to_elegance_shape():
    n = norm(fx.PEARL)
    product = n["product"]
    assert product["category"] == "shawls" and product["slug"] == "pearl-cashmere-shawl"
    assert product["cover_image_url"] == fx.PEARL["image_urls"][0]
    assert product["variants"][0]["stock"] == 0 and product["variants"][0]["color"] == "Pearl White"
    assert n["source_price"] == 189.0 and n["source_currency"] == "AUD"
    assert "price" not in product  # never converted into PKR
    assert {"price", "stock"} <= set(n["missing_fields"])
    assert n["source_attributes"] == {"origin": "Nepal"}


def test_missing_price_and_details_are_flagged_not_invented():
    n = norm(fx.IVORY_STOLE_NO_PRICE)
    assert n["source_price"] is None and n["source_currency"] is None
    assert {"source_price", "material", "sizing", "weight"} <= set(n["missing_fields"])
    assert n["product"]["category"] == "stoles" and n["product"]["material"] is None


def test_price_without_currency_flags_currency():
    n = norm({**fx.PEARL, "currency": None})
    assert "source_currency" in n["missing_fields"]


def test_markup_and_control_characters_are_stripped():
    n = norm({**fx.PEARL, "title": "<b>Pearl</b> Shawl\x00", "description": "<script>x()</script>Soft  wool"})
    assert n["product"]["name"] == "Pearl Shawl"
    assert "<" not in n["product"]["main_description"]


def test_images_on_unlisted_hosts_are_dropped():
    n = norm({**fx.PEARL, "image_urls": ["https://evil.example/a.jpg", "http://shop.example/b.jpg", fx.PEARL["image_urls"][0]]})
    assert n["product"]["images"] == [fx.PEARL["image_urls"][0]]
    with pytest.raises(InvalidSourceData):
        norm({**fx.PEARL, "image_urls": ["https://evil.example/a.jpg"]})


def test_content_hash_tracks_source_changes():
    assert norm(fx.PEARL)["source_content_hash"] == norm(fx.PEARL)["source_content_hash"]
    assert norm(fx.PEARL)["source_content_hash"] != norm({**fx.PEARL, "price": 200.0})["source_content_hash"]


def test_off_source_product_url_rejected():
    with pytest.raises(UnsafeURL):
        norm({**fx.PEARL, "url": "https://evil.example/products/x"})


@pytest.mark.parametrize("path", ["/", "//evil.example/products/x", "/products/../admin", "/products/a b", "products/a",
                                  "https://evil.example/products/x", "/collections/all"])
def test_job_path_must_be_product_path(path):
    with pytest.raises(InvalidSourceData):
        source_url_for_path(path, POLICY)


def test_source_categories_map_to_their_elegance_category():
    assert norm(fx.PEARL)["product"]["category"] == "shawls"
    assert norm(fx.IVORY_STOLE_NO_PRICE)["product"]["category"] == "stoles"
    assert norm({**fx.PEARL, "category": "scarf"})["product"]["category"] == "scarves"


def test_staged_validation_rejects_unknown_categories():
    import pytest as _pytest
    from pydantic import ValidationError
    from schemas.ingestion_schema import StagedProductDraft
    draft = norm(fx.PEARL)["product"]
    assert StagedProductDraft.model_validate({**draft, "category": "scarves"}).category.value == "scarves"
    with _pytest.raises(ValidationError):
        StagedProductDraft.model_validate({**draft, "category": "wallets"})


def test_apex_and_www_urls_canonicalize_to_the_same_product():
    policy = SourcePolicy("shop.example", True, extra_hosts=frozenset({"www.shop.example"}))
    apex = normalize(ProductShawl.model_validate(fx.PEARL), policy=policy, source_product_id=None, fetched_at=NOW)
    www = normalize(ProductShawl.model_validate({**fx.PEARL, "url": fx.PEARL["url"].replace("shop.example", "www.shop.example")}),
                    policy=policy, source_product_id=None, fetched_at=NOW)
    assert apex["source_url"] == www["source_url"] == "https://shop.example/products/pearl-cashmere-shawl"
    assert apex["source_content_hash"] == www["source_content_hash"]


def test_unlisted_sibling_host_is_rejected_by_normalize():
    policy = SourcePolicy("shop.example", True, extra_hosts=frozenset({"www.shop.example"}))
    for host in ("evil.shop.example", "shop.example.evil.example", "shop.example@evil.example"):
        with pytest.raises(UnsafeURL):
            normalize(ProductShawl.model_validate({**fx.PEARL, "url": f"https://{host}/products/x"}),
                      policy=policy, source_product_id=None, fetched_at=NOW)


def test_slugify():
    assert slugify("Pearl & Ivory — Shawl!") == "pearl-ivory-shawl"


# ---- end-to-end job processing -------------------------------------------

@pytest.mark.asyncio
async def test_successful_ingestion_stages_pending_review(db):
    await enqueue(db)
    job = await run(db)
    assert job["status"] == "succeeded" and job["result"]["outcome"] == "created"
    staged = await db.staged_products.find_one({})
    assert staged["status"] == "pending_review"
    assert staged["source_product_id"] == "7712345678"
    assert staged["dedupe_key"] == "id:7712345678"
    assert staged["ingestion_job_id"] == job["_id"]
    assert staged["source_url"] == "https://shop.example/products/pearl-cashmere-shawl"
    assert staged["product_id"] is None
    assert await db.products.count_documents({}) == 0  # nothing reaches the catalogue


@pytest.mark.asyncio
async def test_page_images_are_merged_into_staged_product(db):
    await enqueue(db)
    await run(db)
    images = (await db.staged_products.find_one({}))["product"]["images"]
    assert "https://shop.example/cdn/shop/files/pearl_detail_1800x.jpg" in images


@pytest.mark.asyncio
async def test_rerunning_same_job_does_not_duplicate(db):
    job = await enqueue(db)
    await run(db)
    await jobs.requeue_job(db, job["_id"])
    again = await run(db)
    assert again["result"]["outcome"] == "unchanged"
    assert await db.staged_products.count_documents({}) == 1


@pytest.mark.asyncio
async def test_same_product_under_a_new_job_is_not_duplicated(db):
    await enqueue(db, idempotency_key="one")
    await run(db)
    await enqueue(db, idempotency_key="two")
    await run(db)
    assert await db.staged_products.count_documents({}) == 1


@pytest.mark.asyncio
async def test_changed_source_updates_pending_but_not_reviewed_products(db):
    await enqueue(db, idempotency_key="1")
    await run(db)
    await enqueue(db, idempotency_key="2")
    changed = await run(db, {**fx.PEARL, "price": 250.0})
    assert changed["result"]["outcome"] == "updated"
    assert (await db.staged_products.find_one({}))["source_price"] == 250.0

    await db.staged_products.update_one({}, {"$set": {"status": "approved"}})
    await enqueue(db, idempotency_key="3")
    flagged = await run(db, {**fx.PEARL, "price": 300.0})
    assert flagged["result"]["outcome"] == "source_changed"
    doc = await db.staged_products.find_one({})
    assert doc["source_price"] == 250.0 and doc["status"] == "approved" and doc["latest_source_hash"]


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [fx.INVALID_NO_TITLE, fx.INVALID_CATEGORY, None])
async def test_invalid_source_data_fails_terminally_and_stages_nothing(db, data):
    await enqueue(db)
    job = await run(db, data)
    assert job["status"] == "failed" and job["attempts"] == 1
    assert await db.staged_products.count_documents({}) == 0


@pytest.mark.asyncio
async def test_transient_fetch_failure_retries_then_fails_terminally(db):
    await enqueue(db, max_attempts=2)
    first = await run(db, fetcher=make_fetcher(503, ""))
    assert first["status"] == "retrying"
    assert await worker.process_next_job(db, "w", make_fetcher(503, ""), FixtureExtractor(fx.PEARL)) is None  # backoff
    await db.ingestion_jobs.update_one({}, {"$set": {"available_at": NOW}})
    last = await run(db, fetcher=make_fetcher(503, ""))
    assert last["status"] == "failed" and "503" in last["last_error"]


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
    assert job["status"] == "retrying" and "timed out" in job["last_error"]


@pytest.mark.asyncio
async def test_unauthorized_source_never_fetches(db):
    def handler(request):
        raise AssertionError("must not fetch")

    fetcher = SafeFetcher(SourcePolicy("shop.example", False), rate_limiter=DomainRateLimiter(0),
                          client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await enqueue(db)
    job = await run(db, fetcher=fetcher)
    assert job["status"] == "failed" and "authorized" in job["last_error"]


@pytest.mark.asyncio
async def test_crashed_worker_job_is_recovered_and_completed(db):
    long_ago = NOW - timedelta(hours=3)
    await enqueue(db, now=long_ago)
    assert await jobs.claim_next(db, "dead", long_ago)  # worker dies holding the lease
    assert await run(db) is None  # recovery requeues with backoff; not claimable yet
    assert (await db.ingestion_jobs.find_one({}))["status"] == "retrying"
    await db.ingestion_jobs.update_one({}, {"$set": {"available_at": NOW}})
    job = await run(db)
    assert job["status"] == "succeeded" and job["attempts"] == 2
