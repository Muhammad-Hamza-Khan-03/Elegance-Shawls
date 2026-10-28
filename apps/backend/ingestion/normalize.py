"""Quill scraper output -> staged Elegance product.

Remote text is untrusted: markup is stripped, whitespace collapsed, lengths capped, and
image URLs must pass the source image allowlist. Source price is kept as provenance and is
never converted to PKR; the retail price and stock are supplied by a human at approval.
"""
import re
import unicodedata
from datetime import datetime

from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from ingestion.quill_scraper import ProductShawl, normalize_shopify_product_url
from ingestion.safe_fetch import SourcePolicy, is_allowed_image_url, validate_url
from models.ingestion_model import content_hash
from schemas.ingestion_schema import StagedProductDraft

# Approved policy: scarf, shawl, wrap, pashmina and stole all land in the shawls category.
CATEGORY_MAP = {"shawl": "shawls", "stole": "shawls"}
MAX_IMAGES = 12
PATH_PATTERN = re.compile(r"^/products/[A-Za-z0-9][A-Za-z0-9._~%-]{0,200}$")
_ID_PATTERNS = (
    re.compile(r'"product"\s*:\s*\{\s*"id"\s*:\s*(\d{4,20})'),
    re.compile(r'data-product-id=["\'](\d{4,20})["\']'),
)


class InvalidSourceData(Exception):
    """The source page or scraper output cannot become a staged product. Not retryable."""


def clean_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = BeautifulSoup(str(value), "html.parser").get_text(separator=" ")
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in "\n\t")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] or None


def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug[:170].strip("-")


def source_url_for_path(path: str, policy: SourcePolicy) -> str:
    """Jobs carry only a product path; the host always comes from configuration."""
    if not PATH_PATTERN.fullmatch(path):
        raise InvalidSourceData("Job path must look like /products/<handle>")
    url = f"https://{policy.domain}{path}"
    validate_url(url, policy)
    return url


def extract_source_product_id(raw_html: str) -> str | None:
    for pattern in _ID_PATTERNS:
        match = pattern.search(raw_html)
        if match:
            return match.group(1)
    return None


def _price(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value >= 0 else None


def _currency(value) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z]{3}", value.strip()):
        return value.strip().upper()
    return None


def normalize(
    scraped: ProductShawl,
    *,
    policy: SourcePolicy,
    source_product_id: str | None,
    fetched_at: datetime,
) -> dict:
    """Return the fields needed by pipeline.stage_product."""
    validate_url(scraped.url, policy)
    source_url = normalize_shopify_product_url(scraped.url.split("?")[0].split("#")[0])
    # Hosts of one source are the same catalogue: key everything on the canonical host so
    # apex and www URLs of a product cannot stage twice.
    parts = urlsplit(source_url)
    source_url = parts._replace(netloc=policy.domain).geturl()

    name = clean_text(scraped.title, 160)
    if not name:
        raise InvalidSourceData("Product has no usable title")
    slug = slugify(name)
    if not slug:
        raise InvalidSourceData("Product title cannot be turned into a slug")

    images: list[str] = []
    for url in scraped.image_urls:
        if url not in images and is_allowed_image_url(url, policy):
            images.append(url)
    images = images[:MAX_IMAGES]
    if not images:
        raise InvalidSourceData("Product has no images on an allowed host")

    color = clean_text(scraped.color, 100)
    material = clean_text(scraped.material, 200)
    sizing = clean_text(scraped.sizing, 200)
    weight = clean_text(scraped.weight, 100)
    source_price = _price(scraped.price)
    source_currency = _currency(scraped.currency)

    draft = StagedProductDraft(
        name=name,
        slug=slug,
        cover_image_url=images[0],
        images=images,
        main_description=clean_text(scraped.description, 5000),
        category=CATEGORY_MAP[scraped.category],
        material=material,
        sizing=sizing,
        weight=weight,
        variants=[{
            "name": color or "Default",
            "color": color,
            "image_url": images[0],
            "stock": 0,
        }],
    )

    # The retail price and stock always need a person; the rest is informational.
    missing = ["price", "stock"]
    if source_price is None:
        missing.append("source_price")
    if source_price is not None and source_currency is None:
        missing.append("source_currency")
    for field_name, value in (("material", material), ("sizing", sizing), ("weight", weight)):
        if not value:
            missing.append(field_name)

    product = draft.model_dump(mode="json")
    attributes = {"origin": clean_text(scraped.origin, 100)}
    return {
        "source_url": source_url,
        "source_product_id": source_product_id,
        "source_price": source_price,
        "source_currency": source_currency,
        "product": product,
        "source_attributes": attributes,
        "missing_fields": missing,
        "source_content_hash": content_hash({
            "product": product, "attributes": attributes,
            "price": source_price, "currency": source_currency,
        }),
        "fetched_at": fetched_at,
    }
