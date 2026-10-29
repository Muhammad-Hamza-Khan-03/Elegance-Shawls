from datetime import datetime, timezone

import pytest

from ingestion.normalize import InvalidSourceData, normalize, slugify, source_url_for_path
from ingestion.quill_scraper import ProductShawl
from ingestion.safe_fetch import SourcePolicy, UnsafeURL
from tests.fixtures.ingestion import scraped_products as fx

POLICY = SourcePolicy("shop.example", True)
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


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
