from pathlib import Path

import httpx
import pytest

from ingestion import quill_scraper as qs
from ingestion.safe_fetch import DomainRateLimiter, SafeFetcher, SourcePolicy

FIXTURE = (Path(__file__).parent / "fixtures/ingestion/product_page.html").read_text()
BASE = "https://shop.example/products/pearl-cashmere-shawl"


def test_sanitize_strips_scripts_and_finds_product_images_only():
    html, images = qs.sanitize_product_html(FIXTURE, BASE)
    assert "<script" not in html and "steal()" not in html and "header" not in html.lower().split("main")[0]
    assert "<img" not in html
    assert images == [
        "https://shop.example/cdn/shop/files/pearl_back_1800x.jpg",
        "https://shop.example/cdn/shop/files/pearl_front_1800x.jpg",
    ]


def test_extract_images_from_raw_html_finds_photoswipe_source():
    images = qs.extract_shopify_product_images(FIXTURE, BASE)
    assert "https://shop.example/cdn/shop/files/pearl_detail_1800x.jpg" in images
    assert not any("logo" in i for i in images)


def test_image_heuristic():
    assert not qs.is_likely_product_image("https://x/cdn/shop/files/logo.png")
    assert qs.is_likely_product_image("https://x/cdn/shop/files/a")
    assert qs.is_likely_product_image("https://x/a.WEBP")
    assert not qs.is_likely_product_image("https://x/a.gif")


@pytest.mark.parametrize("url,ok", [
    ("https://s.example/products/a", True),
    ("https://s.example/collections/all", False),
    ("https://s.example/cdn/shop/products/a.jpg", False),
    ("https://s.example/products/a.png", False),
])
def test_product_url_validation(url, ok):
    assert qs.is_valid_shopify_product_url(url) is ok


def test_product_url_normalization_drops_query_and_variants():
    assert qs.normalize_shopify_product_url("https://s.example/collections/x/products/a?variant=1") == \
        "https://s.example/products/a"
    assert qs.normalize_shopify_product_url("https://s.example/products/") == "https://s.example/products/"


def test_collection_links_extracted_and_normalized():
    links = qs.extract_product_links(FIXTURE, BASE)
    assert links == {
        "https://shop.example/products/pearl-cashmere-shawl",
        "https://shop.example/products/ivory-stole",
    }


@pytest.mark.asyncio
async def test_fetch_clean_html_goes_through_safe_fetcher():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=FIXTURE)

    async def dns(_):
        return ["93.184.216.34"]

    fetcher = SafeFetcher(
        SourcePolicy("shop.example", True), resolver=dns, rate_limiter=DomainRateLimiter(0),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    page = await qs.fetch_product_page_clean_html(fetcher, BASE)
    assert page["source_url"] == BASE
    assert len(page["images"]) == 3 and "<script" not in page["html"]


@pytest.mark.asyncio
async def test_unconfigured_extractor_fails_loudly():
    with pytest.raises(qs.ExtractorNotConfigured):
        await qs.UnconfiguredExtractor().extract(source_url=BASE, sanitized_html="", text="")
