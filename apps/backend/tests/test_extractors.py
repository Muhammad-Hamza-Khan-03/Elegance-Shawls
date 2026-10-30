from pathlib import Path

import pytest

from ingestion.extractors import ShopifyHtmlExtractor, infer_category, parse_spec_lines
from ingestion.normalize import InvalidSourceData
from ingestion.safe_fetch import SourcePolicy

FIX = Path(__file__).parent / "fixtures/ingestion/shopify"
URL = "https://shop.example/products/x"
POLICY = SourcePolicy("shop.example", True, frozenset({"cdn.shopify.com"}), frozenset({"www.shop.example"}))


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


@pytest.mark.parametrize("candidates,expected", [
    (("Wool Scarf",), "scarf"), (("Merino Scarves",), "scarf"), (("SCARF",), "scarf"),
    ((None, "Plain title", "/products/winter-scarf-grey"), "scarf"),
    (("Cashmere Shawl",), "shawl"), (("Cashmere Shawls",), "shawl"), (("Silk Wrap",), "shawl"),
    (("Pashmina",), "shawl"), (("Pashminas",), "shawl"), (("Accessories", "Evening wrap in navy"), "shawl"),
    (("Silk Stole",), "stole"), (("Stoles",), "stole"),
])
def test_explicit_terms_map_to_their_category(candidates, expected):
    assert infer_category(*candidates) == expected


@pytest.mark.parametrize("candidates", [
    ("Leather Wallet",), ("Wool Blanket",), ("Scarfing Tool",), ("Wrapper",), ("Handbag", "Accessories"), (None, None),
])
def test_no_explicit_term_is_not_guessed(candidates):
    assert infer_category(*candidates) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("title,expected", [
    ("Alpine Scarf", "scarves"), ("Alpine Scarves", "scarves"), ("Silk Stole", "stoles"), ("Silk Stoles", "stoles"),
    ("Pashmina Wrap", "shawls"), ("Heritage Shawl", "shawls"), ("Heritage Shawls", "shawls"), ("Pashmina", "shawls"),
])
async def test_every_approved_term_stages_into_its_category(title, expected):
    html = f'''<html><head><meta property="og:title" content="{title}">
    <meta property="og:description" content="Plain description."><meta property="og:image" content="https://cdn.shopify.com/a.jpg">
    </head></html>'''
    from ingestion.normalize import normalize
    from ingestion.quill_scraper import ProductShawl
    from datetime import datetime, timezone
    data = await ShopifyHtmlExtractor().extract(source_url=URL, sanitized_html="", text="", raw_html=html)
    scraped = ProductShawl.model_validate({**data, "url": URL})
    staged = normalize(scraped, policy=POLICY, source_product_id=None, fetched_at=datetime.now(timezone.utc))
    assert staged["product"]["category"] == expected


@pytest.mark.asyncio
async def test_nothing_is_inferred_beyond_what_the_page_states():
    html = '''<html><head><meta property="og:title" content="Fine Merino Wool Scarf, Large">
    <meta property="og:description" content="Beautiful, warm and generously sized. Imported from overseas.">
    <script type="application/ld+json">{"@type":"Product","name":"Fine Merino Wool Scarf, Large",
    "offers":{"@type":"Offer","availability":"https://schema.org/InStock","price":"59.00"}}</script></head></html>'''
    data = await ShopifyHtmlExtractor().extract(source_url=URL, sanitized_html="", text="", raw_html=html)
    # "Merino Wool" in the title is not a material, "Large" is not a size, "Imported" is not an origin.
    assert data["material"] is None and data["sizing"] is None and data["weight"] is None and data["origin"] is None
    assert data["color"] is None
    assert data["price"] == 59.0 and data["currency"] is None  # price without a stated currency stays unknown
    assert "stock" not in data and "availability" not in str(data)  # InStock never becomes stock
