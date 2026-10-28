"""Deterministic product-field extraction for Shopify storefront pages (no LLM, no browser).

Sources are tried in order of reliability, per field, and the first usable value wins:

1. schema.org JSON-LD ``Product`` (also inside ``@graph`` / ``ProductGroup``)
2. Open Graph / ``product:*`` meta tags that Shopify themes emit
3. Theme selectors (``[itemprop]``, ``h1``, common description containers)
4. ``Label: value`` spec lines inside the description (material, size, weight, origin)

Everything read from the page is untrusted: JSON is parsed with ``json.loads`` only, values
are type-checked, and nothing is executed or fetched. Stock is never inferred from
availability markup, so staged products always need a human to set stock.
"""
import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ingestion.normalize import InvalidSourceData

PRODUCT_TYPES = {"product", "productgroup"}
DESCRIPTION_SELECTORS = (
    "[itemprop=description]", ".product__description", ".product-single__description",
    ".product-description", ".rte", "[data-product-description]",
)
TITLE_SELECTORS = ("[itemprop=name]", "h1.product__title", ".product__title", ".product-single__title", "h1")
PRICE_SELECTORS = ("[itemprop=price]", ".price-item--regular", ".price-item--sale", ".product__price", ".price")
SPEC_LABELS = {
    "material": r"material|fabric|composition",
    "sizing": r"size|sizes|dimensions?|measurements?",
    "weight": r"weight|gsm",
    "origin": r"country of origin|origin",
}
# Approved policy: the first explicit term in the category, title or URL handle decides the category.
# Nothing else is inferred; a page with none of these terms fails instead of being guessed.
CATEGORY_TERMS = re.compile(r"\b(shawls?|wraps?|pashminas?|scarf|scarves|stoles?)\b", re.I)


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    if isinstance(value, str):
        match = re.search(r"\d[\d,]*(?:\.\d+)?|\.\d+", value)
        if match:
            try:
                return float(match.group(0).replace(",", ""))
            except ValueError:
                return None
    return None


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _json_ld_products(soup: BeautifulSoup) -> list[dict]:
    found: list[dict] = []

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            kinds = {str(t).lower() for t in _as_list(node.get("@type"))}
            if kinds & PRODUCT_TYPES:
                found.append(node)
            visit(node.get("@graph"))

    for script in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        try:
            visit(json.loads(script.string or script.get_text() or ""))
        except (ValueError, RecursionError):
            continue  # a broken block must not hide the others
    return found


def _image_urls(value: Any, base_url: str) -> list[str]:
    urls = []
    for item in _as_list(value):
        raw = item.get("url") or item.get("contentUrl") if isinstance(item, dict) else item
        if isinstance(raw, str) and raw.strip():
            urls.append(urljoin(base_url, raw.strip().split("#")[0]))
    return urls


def _offer(product: dict) -> tuple[float | None, str | None]:
    for offer in _as_list(product.get("offers")):
        if not isinstance(offer, dict):
            continue
        price = _number(offer.get("price"))
        if price is None:
            price = _number(offer.get("lowPrice"))
        if price is not None:
            return price, _text(offer.get("priceCurrency"))
    return None, None


def _quantity(value: Any) -> str | None:
    if isinstance(value, dict):
        amount, unit = _text(value.get("value")), _text(value.get("unitText") or value.get("unitCode"))
        return f"{amount} {unit}".strip() if amount else None
    return _text(value)


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and _text(tag.get("content")):
            return _text(tag["content"])
    return None


def _first_text(soup: BeautifulSoup, selectors: tuple[str, ...], attr: str | None = None) -> str | None:
    for selector in selectors:
        for node in soup.select(selector):
            value = _text(node.get(attr)) if attr and node.get(attr) else None
            value = value or _text(node.get_text(separator="\n", strip=True))
            if value:
                return value
    return None


def parse_spec_lines(text: str | None) -> dict[str, str]:
    """Pull ``Label: value`` facts out of free text. First match per label wins."""
    specs: dict[str, str] = {}
    if not text:
        return specs
    for line in re.split(r"[\n\r;•·]+", text):
        line = line.strip(" -–\t")
        made_in = re.match(r"made in\s+([A-Za-z][A-Za-z .'-]{1,60})$", line, re.I)
        if made_in and "origin" not in specs:
            specs["origin"] = made_in.group(1).strip()
            continue
        for key, labels in SPEC_LABELS.items():
            match = re.match(rf"^(?:{labels})\s*[:\-–]\s*(.{{1,200}})$", line, re.I)
            if match and key not in specs:
                specs[key] = match.group(1).strip()
                break
    return specs


def infer_category(*candidates: str | None) -> str | None:
    for candidate in candidates:
        match = candidate and CATEGORY_TERMS.search(candidate)
        if match:
            term = match.group(1).lower()
            return "scarf" if term.startswith("scarf") or term == "scarves" else "stole" if term.startswith("stole") else "shawl"
    return None


class ShopifyHtmlExtractor:
    """FieldExtractor for Shopify product pages served as static HTML."""

    async def extract(self, *, source_url: str, sanitized_html: str, text: str, raw_html: str = "") -> dict | None:
        if not raw_html.strip():
            raise InvalidSourceData("No page HTML to extract from")
        soup = BeautifulSoup(raw_html, "html.parser")
        product = (_json_ld_products(soup) or [{}])[0]

        title = _text(product.get("name")) or _meta(soup, "og:title") or _first_text(soup, TITLE_SELECTORS)
        description = (
            _text(product.get("description"))
            or _first_text(soup, DESCRIPTION_SELECTORS)
            or _meta(soup, "og:description", "description")
        )
        if not title:
            raise InvalidSourceData("Page has no product title (JSON-LD, og:title or heading)")
        if not description:
            raise InvalidSourceData("Page has no product description")

        price, currency = _offer(product)
        if price is None:
            price = _number(_meta(soup, "product:price:amount", "og:price:amount")) or _number(
                _first_text(soup, PRICE_SELECTORS, attr="content"))
        currency = currency or _meta(soup, "product:price:currency", "og:price:currency")
        if not (_text(currency) and re.fullmatch(r"[A-Za-z]{3}", _text(currency) or "")):
            currency = None

        images = _image_urls(product.get("image"), source_url) or _image_urls(_meta(soup, "og:image:secure_url", "og:image"), source_url)

        specs = parse_spec_lines(description)
        category = infer_category(_text(product.get("category")), title, source_url)
        if not category:
            raise InvalidSourceData("Cannot determine category (expected scarf, shawl, wrap, pashmina or stole) from the page")

        return {
            "title": title,
            "description": description,
            "image_urls": images,
            "category": category,
            "color": _text(product.get("color")),
            "material": _text(product.get("material")) or specs.get("material"),
            "sizing": specs.get("sizing"),
            "weight": _quantity(product.get("weight")) or specs.get("weight"),
            "origin": specs.get("origin"),
            "price": price,
            "currency": currency.upper() if currency else None,
        }
