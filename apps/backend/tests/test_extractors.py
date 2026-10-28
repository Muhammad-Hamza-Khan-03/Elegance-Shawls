from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from database.db import ensure_indexes
from ingestion import jobs, worker
from ingestion.extractors import ShopifyHtmlExtractor, infer_category, parse_spec_lines
from ingestion.normalize import InvalidSourceData
from ingestion.safe_fetch import DomainRateLimiter, SafeFetcher, SourcePolicy

FIX = Path(__file__).parent / "fixtures/ingestion/shopify"
URL = "https://shop.example/products/x"
POLICY = SourcePolicy("shop.example", True, frozenset({"cdn.shopify.com"}))


def load(name):
    return (FIX / name).read_text()


async def extract(name, url=URL):
    html = load(name)
    return await ShopifyHtmlExtractor().extract(source_url=url, sanitized_html="", text="", raw_html=html)


@pytest.mark.asyncio
async def test_json_ld_product_is_preferred_and_complete():
    data = await extract("jsonld_full.html")
    assert data["title"] == "Heritage Wool Shawl"  # JSON-LD beats og:title
    assert data["price"] == 1089.5 and data["currency"] == "AUD"
    assert data["category"] == "shawl" and data["color"] == "Charcoal"
    assert data["material"] == "100% Merino Wool" and data["sizing"] == "70 x 200 cm"
    assert data["weight"] == "280gsm" and data["origin"] == "Nepal"
    assert data["image_urls"] == [
        "https://cdn.shopify.com/s/files/1/0001/products/heritage_front.jpg?v=1",
        "https://cdn.shopify.com/s/files/1/0001/products/heritage_back.jpg",
    ]


@pytest.mark.asyncio
async def test_graph_product_group_aggregate_offer_and_quantity_weight():
    data = await extract("jsonld_graph.html")
    assert data["title"] == "Silk Stole" and data["category"] == "stole"
    assert data["price"] == 45.0 and data["currency"] == "AUD"
    assert data["weight"] == "90 g" and data["material"] == "Silk"
    assert data["image_urls"] == ["https://cdn.shopify.com/s/files/silk.jpg"]


@pytest.mark.asyncio
async def test_meta_tag_fallback():
    data = await extract("meta_only.html", "https://shop.example/products/ivory-pashmina")
    assert data["title"] == "Ivory Pashmina Wrap" and data["category"] == "shawl"
    assert data["price"] == 120.0 and data["currency"] == "AUD"
    assert data["image_urls"] == ["https://cdn.shopify.com/s/files/ivory.jpg?v=3"]
    assert data["material"] == "Pashmina blend"


@pytest.mark.asyncio
async def test_selector_fallback_leaves_unknown_currency_unset():
    data = await extract("selectors_only.html")
    assert data["title"] == "Blush Stole" and data["category"] == "stole"
    assert data["price"] == 1200.0 and data["currency"] is None  # currency is never guessed
    assert data["sizing"] == "70x180cm" and data["image_urls"] == []


@pytest.mark.asyncio
async def test_malformed_json_ld_falls_back_to_meta():
    data = await extract("malformed_jsonld.html")
    assert data["title"] == "Broken Shawl" and data["description"] == "Fallback description"
    assert data["price"] is None


@pytest.mark.asyncio
async def test_hostile_values_are_ignored_or_inert():
    data = await extract("hostile.html", "https://shop.example/products/evil-shawl")
    assert data["price"] is None and data["currency"] is None
    assert data["material"] is None and data["weight"] is None
    # Markup survives extraction as plain data; normalize() strips it later. Nothing is executed or fetched.
    assert "Evil Shawl" in data["title"]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,message", [
    ("empty.html", "no product title"),
    ("no_category.html", "category"),
])
async def test_unusable_pages_raise_invalid_source_data(name, message):
    with pytest.raises(InvalidSourceData, match=message):
        await extract(name, "https://shop.example/products/wallet")


@pytest.mark.asyncio
async def test_blank_html_rejected():
    with pytest.raises(InvalidSourceData):
        await ShopifyHtmlExtractor().extract(source_url=URL, sanitized_html="", text="", raw_html="  ")


def test_spec_line_parsing():
    specs = parse_spec_lines("Fabric: Wool; Dimensions - 70x200cm\nGSM: 300\nCountry of origin: India")
    assert specs == {"material": "Wool", "sizing": "70x200cm", "weight": "300", "origin": "India"}
    assert parse_spec_lines("Made in Nepal")["origin"] == "Nepal"
    assert parse_spec_lines(None) == {}
    assert parse_spec_lines("Not a spec line at all") == {}


def test_category_inference():
    assert infer_category("Silk Stoles") == "stole"
    assert infer_category(None, "Wool Scarf", "/x") == "shawl"
    assert infer_category("Leather Wallet") is None


# ---- through the worker with the real extractor -----------------------------

@pytest_asyncio.fixture
async def db():
    database = AsyncMongoMockClient().extract
    await ensure_indexes(database)
    return database


def fetcher_for(html):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    async def dns(_):
        return ["93.184.216.34"]

    return SafeFetcher(POLICY, resolver=dns, rate_limiter=DomainRateLimiter(0),
                       client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.asyncio
async def test_worker_stages_a_product_using_the_deterministic_extractor(db):
    await jobs.create_job(db, source_id="primary", path="/products/heritage-wool-shawl")
    job = await worker.process_next_job(db, "w", fetcher_for(load("jsonld_full.html")), ShopifyHtmlExtractor())
    assert job["status"] == "succeeded"
    staged = await db.staged_products.find_one({})
    assert staged["status"] == "pending_review" and staged["source_product_id"] == "8800112233"
    assert staged["source_price"] == 1089.5 and staged["source_currency"] == "AUD"
    assert staged["product"]["name"] == "Heritage Wool Shawl" and staged["product"]["material"] == "100% Merino Wool"
    assert staged["product"]["cover_image_url"].startswith("https://cdn.shopify.com/")
    assert "price" in staged["missing_fields"] and "stock" in staged["missing_fields"]
    assert await db.products.count_documents({}) == 0


@pytest.mark.asyncio
async def test_worker_strips_hostile_markup_and_offsite_images(db):
    await jobs.create_job(db, source_id="primary", path="/products/evil-shawl")
    job = await worker.process_next_job(db, "w", fetcher_for(load("hostile.html")), ShopifyHtmlExtractor())
    assert job["status"] == "succeeded"
    staged = await db.staged_products.find_one({})
    assert "<" not in staged["product"]["name"] and "<" not in staged["product"]["main_description"]
    assert staged["product"]["images"] == ["https://cdn.shopify.com/ok.jpg"]  # javascript: and evil.example dropped
    assert staged["status"] == "pending_review"


@pytest.mark.asyncio
async def test_worker_fails_terminally_on_unextractable_page(db):
    await jobs.create_job(db, source_id="primary", path="/products/nothing")
    job = await worker.process_next_job(db, "w", fetcher_for(load("empty.html")), ShopifyHtmlExtractor())
    assert job["status"] == "failed" and job["attempts"] == 1 and "title" in job["last_error"]
    assert await db.staged_products.count_documents({}) == 0
