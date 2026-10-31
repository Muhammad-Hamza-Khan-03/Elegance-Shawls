"""Deterministic, public-only text for embedding a product and its variants.

Only the allowlisted fields below are read; everything else (ids, slug, item_number, images, prices, stock,
status, costs, source/ingestion data, customer/contact/order data, admin fields) is ignored by construction.
Free text is scrubbed of emails, URLs and long digit runs (phone/order numbers) before it is embedded.
"""
import hashlib
import re
import unicodedata
from typing import Any, Mapping

REPRESENTATION_VERSION = "ps-v1"

# Explicit bounds. Over-long free text is truncated (deterministically); malformed input is rejected.
MAX_FIELD_CHARS = {"name": 160, "category": 40, "material": 200, "sizing": 200, "description": 1500,
                   "variant_name": 160, "color": 80, "size": 80, "variant_description": 300}
MAX_VARIANTS = 20
MAX_TEXT_CHARS = 4000

_PRODUCT_FIELDS = (("name", "name"), ("category", "category"), ("material", "material"),
                   ("sizing", "sizing"), ("main_description", "description"))
_VARIANT_FIELDS = (("name", "variant_name"), ("color", "color"), ("size", "size"),
                   ("description", "variant_description"))
_SCRUB = re.compile(r"[^\s@]+@[^\s@]+|https?://\S+|www\.\S+|\+?\d(?:[\s().-]*\d){6,}")


class RepresentationError(ValueError):
    """Input cannot be represented (not a mapping, or no usable name)."""


def _clean(value: Any, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(getattr(value, "value", value))  # enums (category/status) arrive as members
    text = unicodedata.normalize("NFKC", value).casefold()
    text = _SCRUB.sub(" ", text)
    return " ".join(text.split())[:limit].strip()


def _fields(source: Mapping[str, Any], spec) -> list[str]:
    parts = []
    for key, label in spec:
        value = _clean(source.get(key), MAX_FIELD_CHARS[label])
        if value:
            parts.append(f"{label}: {value}")
    return parts


def serialize_product(product: Mapping[str, Any]) -> str:
    if not isinstance(product, Mapping):
        raise RepresentationError("product must be a mapping")
    lines = _fields(product, _PRODUCT_FIELDS)
    if not any(line.startswith("name: ") for line in lines):
        raise RepresentationError("product name is required")
    variants = product.get("variants") or []
    if not isinstance(variants, (list, tuple)) or not all(isinstance(v, Mapping) for v in variants):
        raise RepresentationError("variants must be a list of mappings")
    # Sorted + de-duplicated so storage order never changes the fingerprint.
    rendered = sorted({"variant: " + " | ".join(_fields(v, _VARIANT_FIELDS)) for v in variants
                       if _fields(v, _VARIANT_FIELDS)})
    lines += rendered[:MAX_VARIANTS]
    return "\n".join(lines)[:MAX_TEXT_CHARS]


def fingerprint(text: str) -> str:
    return hashlib.sha256(f"{REPRESENTATION_VERSION}\n{text}".encode("utf-8")).hexdigest()


def represent(product: Mapping[str, Any]) -> dict[str, str]:
    text = serialize_product(product)
    return {"version": REPRESENTATION_VERSION, "text": text, "fingerprint": fingerprint(text)}
