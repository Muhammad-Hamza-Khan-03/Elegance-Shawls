"""Quill scraper output -> staged Elegance product.

Remote text is untrusted: markup is stripped, whitespace collapsed, lengths capped, and
image URLs must pass the source image allowlist. Source price is kept as provenance and is
never converted to PKR; the retail price and stock are supplied by a human at approval.
"""
import re
import html
import unicodedata
from datetime import datetime

from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from ingestion.markdown import html_to_markdown
from ingestion.quill_scraper import ProductShawl, normalize_shopify_product_url
from ingestion.safe_fetch import SourcePolicy, is_allowed_image_url, validate_url
from models.ingestion_model import content_hash
from schemas.ingestion_schema import StagedProductDraft

# Approved policy: scarf/scarves -> scarves, stole/stoles -> stoles, shawl/shawls/wrap/pashmina -> shawls.
CATEGORY_MAP = {"scarf": "scarves", "stole": "stoles", "shawl": "shawls"}
MAX_IMAGES = 12
PATH_PATTERN = re.compile(r"^/products/[A-Za-z0-9][A-Za-z0-9._~%-]{0,200}$")
_ID_PATTERNS = (
    re.compile(r'"product"\s*:\s*\{\s*"id"\s*:\s*(\d{4,20})'),
    re.compile(r'data-product-id=["\'](\d{4,20})["\']'),
)


class InvalidSourceData(Exception):
    """The source page or scraper output cannot become a staged product. Not retryable."""


_SIZE_SUFFIX = re.compile(r"_(?:\d{1,4}x\d{0,4}|x\d{1,4}|pico|icon|thumb|small|compact|medium|large|grande|original|master)(?=\.[A-Za-z0-9]+$)", re.I)


def image_identity(url: str) -> str:
    """Same picture, any size: Shopify serves one file as `x.jpg`, `x_1800x1800.jpg` and `x.jpg?width=1200`."""
    path = urlsplit(url).path.lower()
    name = _SIZE_SUFFIX.sub("", path.rsplit("/", 1)[-1])
    return name or path


def _is_plain(url: str) -> bool:
    parts = urlsplit(url)
    return not parts.query and not _SIZE_SUFFIX.search(parts.path)


def dedupe_images(urls: list[str]) -> list[str]:
    """One URL per picture, in first-seen order, preferring the unresized original with no query."""
    chosen: dict[str, str] = {}
    for url in urls:
        key = image_identity(url)
        if key not in chosen or (_is_plain(url) and not _is_plain(chosen[key])):
            chosen[key] = url
    return list(chosen.values())


def clean_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = BeautifulSoup(str(value), "html.parser").get_text(separator=" ")
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in "\n\t")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] or None


_TAG = re.compile(r"</?[A-Za-z][^>]*>")


def clean_description(value: str | None, limit: int) -> str | None:
    """Description as the safe Markdown subset: structure kept, markup and control characters removed."""
    if value is None:
        return None
    raw = str(value)
    if _TAG.search(raw):
        return html_to_markdown(BeautifulSoup(raw, "html.parser"), limit) or None
    text = "".join(ch for ch in html.unescape(raw) if unicodedata.category(ch)[0] != "C" or ch in "\n\t")
    lines = [re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in text.replace("\r", "").split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text[:limit].rstrip() or None


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

    images = dedupe_images([url for url in scraped.image_urls if is_allowed_image_url(url, policy)])[:MAX_IMAGES]
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
        main_description=clean_description(scraped.description, 5000),
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
