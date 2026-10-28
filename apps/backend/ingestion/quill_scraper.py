"""Scraper helpers ported from quill-store (app/scrapper_utils/scraper.py,
app/models/product_scrapper_model.py).

Ported unchanged in behavior: image heuristics, HTML sanitizing, image extraction and
Shopify product-URL validation/normalization. Deliberate differences:

* No Crawl4AI/OpenAI imports. Fetching goes through ``SafeFetcher`` so SSRF controls
  apply; text-field extraction (an LLM step in quill-store) is the ``FieldExtractor`` seam.
* ``extract_shopify_product_images`` runs on the raw HTML. quill-store ran it on the
  sanitized HTML, from which ``sanitize_product_html`` had already removed every <img>.
* ``print`` replaced by ``logging``; no CSV/DB/notification code.
"""
import logging
import re
from typing import List, Literal, Optional, Protocol, Set, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field

from ingestion.safe_fetch import SafeFetcher

logger = logging.getLogger("ingestion.quill_scraper")

ALLOWED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
IMAGE_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS


class ProductShawl(BaseModel):
    """quill-store ProductShawl. Remote text is untrusted; only declared fields are kept."""
    model_config = ConfigDict(extra="ignore")

    url: str
    title: str
    description: str
    image_urls: List[str] = Field(default_factory=list)
    category: Literal["shawl", "stole"]
    color: Optional[str] = None
    material: Optional[str] = None
    sizing: Optional[str] = None
    weight: Optional[str] = None
    origin: Optional[str] = None
    price: Optional[float] = None
    # Not in quill-store (its prompt assumed AUD). Optional so the currency is never guessed.
    currency: Optional[str] = None


class FieldExtractor(Protocol):
    """Replaces quill-store's LLM step: turn sanitized page text into ProductShawl fields."""

    async def extract(
        self, *, source_url: str, sanitized_html: str, text: str, raw_html: str = ""
    ) -> dict | None: ...


class ExtractorNotConfigured(Exception):
    pass


class UnconfiguredExtractor:
    async def extract(
        self, *, source_url: str, sanitized_html: str, text: str, raw_html: str = ""
    ) -> dict | None:
        raise ExtractorNotConfigured("No FieldExtractor is configured for the ingestion source")


def is_likely_product_image(src: str) -> bool:
    """Quick heuristic to filter obvious non-product images"""
    lower = src.lower()
    if any(
        x in lower
        for x in ["logo", "icon", "placeholder", "avatar", "badge", "payment", "social", "footer"]
    ):
        return False
    if "cdn/shop/files/" in lower or "cdn/shop/products/" in lower:
        return True
    return any(lower.endswith(ext) for ext in ALLOWED_IMAGE_EXTENSIONS)


def sanitize_product_html(raw_html: str, base_url: str) -> Tuple[str, List[str]]:
    """Extract clean content + high-confidence product image URLs"""
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup(["script", "style", "noscript", "iframe", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()

    selectors = [
        ".product__media-wrapper",
        ".product-single__media",
        ".product-media",
        ".swiper-container",
        "[data-product-single-media-wrapper]",
        ".shopify-section--product-media",
        "main",
        ".product",
        "#ProductSection",
        ".product__info-container + .product__media-wrapper",
    ]

    container = None
    for sel in selectors:
        container = soup.select_one(sel)
        if container:
            break
    if not container:
        container = soup.body or soup

    image_urls: Set[str] = set()

    for img in container.find_all("img"):
        for src in [img.get("src"), img.get("data-src"), img.get("data-lazy"), img.get("data-original")]:
            if not src:
                continue
            full = urljoin(base_url, src.split("?")[0].split("#")[0].strip())
            if is_likely_product_image(full):
                image_urls.add(full)

    for img in container.find_all(["img", "source"]):
        srcset = img.get("srcset") or img.get("data-srcset")
        if srcset:
            for part in srcset.split(","):
                url_part = part.strip().split(" ")[0]
                full = urljoin(base_url, url_part.split("?")[0].strip())
                if is_likely_product_image(full):
                    image_urls.add(full)

    for el in container.find_all(style=True):
        style = el["style"]
        if "background-image" in style:
            start = style.find("url(")
            if start != -1:
                end = style.find(")", start)
                if end != -1:
                    url_str = style[start + 4 : end].strip("'\"")
                    full = urljoin(base_url, url_str.split("?")[0])
                    if is_likely_product_image(full):
                        image_urls.add(full)

    sorted_images = sorted(image_urls)

    for img in container.find_all("img"):
        img.decompose()

    return str(container), sorted_images


def is_valid_shopify_product_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    if "/products/" not in path:
        return False
    if path.startswith("/cdn/") or "/cdn/" in path:
        return False
    if path.endswith(IMAGE_EXTENSIONS):
        return False
    return True


def normalize_shopify_product_url(url: str) -> str:
    parsed = urlparse(url)
    parts = parsed.path.split("/")
    if "products" in parts:
        idx = parts.index("products")
        if idx + 1 < len(parts) and parts[idx + 1]:
            return f"{parsed.scheme}://{parsed.netloc}/products/{parts[idx + 1]}"
    return url


def extract_shopify_product_images(
    html_content: str,
    base_url: str,
    prefer_res: tuple = ("1800", "2000", "1500", "1200", "1080"),
    max_images: int = 10,
) -> List[str]:
    """Robust Shopify product image extractor; absolute URLs, prefers high-res variants."""
    soup = BeautifulSoup(html_content, "html.parser")
    images = set()
    base = base_url.rstrip("/") + "/"

    selectors = [
        "[data-photoswipe-src]",
        ".product__main-photos img.photoswipe__image",
        ".product-single__media img",
        "[data-product-single-media-wrapper] img",
        '.product__thumbs a[href*="_1800x"], .product__thumbs a[href*="x1800"]',
        "div[data-product-thumbs] a[href]",
        "[data-product-images] img",
        ".product__media img",
        ".shopify-section--product-media img",
        "#ProductPhoto img, #ProductThumbs a",
    ]

    for sel in selectors:
        for elem in soup.select(sel):
            if src := elem.get("data-photoswipe-src"):
                images.add(urljoin(base, src.split("?")[0].split("#")[0]))

            if elem.name == "a" and (href := elem.get("href")):
                if any(r in href for r in prefer_res) or re.search(r"_\d{3,4}x", href):
                    images.add(urljoin(base, href.split("?")[0].split("#")[0]))

            for img in [elem] if elem.name == "img" else elem.find_all("img"):
                candidates = [img.get("src"), img.get("data-src"), img.get("data-photoswipe-src")]
                srcset = img.get("srcset") or img.get("data-srcset", "")
                if srcset:
                    for part in srcset.split(","):
                        u = part.strip().split(" ")[0]
                        if u.startswith("//"):
                            u = "https:" + u
                        candidates.append(u)

                for cand in [c for c in candidates if c]:
                    clean = urljoin(base, cand.split("?")[0].split("#")[0])
                    if any(res in clean for res in prefer_res) or re.search(r"_\d{4}x", clean):
                        images.add(clean)
                    elif "cdn/shop/products/" in clean or "cdn/shop/files/" in clean:
                        images.add(clean)

    found = sorted(images)[:max_images]
    logger.info("extracted %d images for %s", len(found), base_url)
    return found


def extract_product_links(html: str, page_url: str) -> set[str]:
    """Valid, normalized product links on a collection page (HTML supplied by SafeFetcher)."""
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        full_url = urljoin(page_url, a["href"])
        if is_valid_shopify_product_url(full_url):
            links.add(normalize_shopify_product_url(full_url))
    return links


async def fetch_product_page_clean_html(fetcher: SafeFetcher, product_url: str) -> dict | None:
    """quill-store's fetch_product_page_clean_html over the guarded fetcher."""
    page = await fetcher.fetch(product_url)
    if not page.text.strip():
        return None
    cleaned_html, sanitized_images = sanitize_product_html(page.text, product_url)
    images = sorted(
        set(extract_shopify_product_images(page.text, product_url, max_images=10)) | set(sanitized_images)
    )[:10]
    return {"html": cleaned_html, "raw_html": page.text, "images": images, "source_url": page.url}


def html_to_text(sanitized_html: str) -> str:
    return BeautifulSoup(sanitized_html, "html.parser").get_text(separator="\n", strip=True)
