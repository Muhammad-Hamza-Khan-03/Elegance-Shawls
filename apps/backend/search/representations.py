"""Deterministic text representations of catalogue products and variants for embedding (pure, no I/O).

Only public, approved catalogue fields are accepted as explicit arguments, so price, stock, URLs, ids, timestamps and
private or staged data cannot reach the text. Text is normalised with the same family as catalog.query, fields appear in
a fixed order with fixed labels, absent optional fields are omitted, and an over-long text fails loudly instead of being
truncated. Persisting and re-embedding on version change belong to S4b: this module only exposes pure values and hashes.
"""
import hashlib
import unicodedata
from dataclasses import dataclass

from catalog.query import normalize
from models.relational_model import ATTRIBUTE_KEYS

REPRESENTATION_VERSION = "catalog-text-v1"
MAX_CHARS = 4000
APPROVED_SOURCES = ("staff_approved", "supplier_declared", "imported")  # visual_suggestion is never embedded


class RepresentationTooLong(ValueError):
    """The text exceeds MAX_CHARS. Shorten the catalogue field; nothing is silently truncated."""


@dataclass(frozen=True)
class Representation:
    kind: str  # "product" | "variant"
    version: str
    text: str
    sha256: str  # over version + text, so a version bump always changes the hash


def clean(value: str | None) -> str:
    """Same normalisation as catalog.query, then control chars and whitespace runs collapsed to single spaces."""
    text = normalize(value or "")
    text = "".join(" " if unicodedata.category(c).startswith("C") else c for c in text)  # \n, \t, other controls
    return " ".join(text.split())


def _attributes(attributes) -> list[str]:
    """One `attr.<key>: a; b` line per key, keys in vocabulary order, values deduplicated and sorted."""
    values: dict[str, set[str]] = {}
    for attr in attributes:
        if attr.key not in ATTRIBUTE_KEYS:
            raise ValueError(f"unknown attribute key {attr.key!r}")
        value = clean(attr.value)
        if value and attr.source in APPROVED_SOURCES:
            values.setdefault(attr.key, set()).add(value)
    return [f"attr.{key}: {'; '.join(sorted(values[key]))}" for key in ATTRIBUTE_KEYS if key in values]


def _build(kind: str, fields: list[tuple[str, str | None]], attributes) -> Representation:
    lines = [f"type: {kind}"] + [f"{label}: {text}" for label, value in fields if (text := clean(value))]
    text = "\n".join(lines + _attributes(attributes))
    if len(text) > MAX_CHARS:
        raise RepresentationTooLong(f"{kind} representation is {len(text)} characters (max {MAX_CHARS})")
    digest = hashlib.sha256(f"{REPRESENTATION_VERSION}\n{text}".encode("utf-8")).hexdigest()
    return Representation(kind, REPRESENTATION_VERSION, text, digest)


def product_representation(name: str, category: str | None = None, material: str | None = None,
                           description: str | None = None, attributes=()) -> Representation:
    """`attributes`: product-level rows with .key, .value, .source (for example catalog.attributes.Attribute)."""
    if not clean(name):
        raise ValueError("a product needs a name")
    return _build("product", [("name", name), ("category", category), ("material", material),
                              ("description", description)], attributes)


def variant_representation(product_name: str, variant_name: str | None = None, color: str | None = None,
                           category: str | None = None, material: str | None = None, attributes=()) -> Representation:
    """`attributes`: this variant's own rows only. No ids, so equal variants of any product share a text."""
    if not clean(product_name):
        raise ValueError("a variant needs its product name")
    return _build("variant", [("product", product_name), ("category", category), ("material", material),
                              ("variant", variant_name), ("color", color)], attributes)
