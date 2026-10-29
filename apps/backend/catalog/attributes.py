"""Canonical catalogue attributes: the controlled keys, provenance and the deterministic backfill rules.

Only the reviewed vocabulary (vocab.yaml) resolves a value. Composition, authenticity, pattern, occasion, season and
style are never inferred from names, descriptions or images here: they exist as keys for approved sources only.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime

from catalog.query import Vocabulary, load_vocabulary
from models.relational_model import ATTRIBUTE_KEYS, ATTRIBUTE_SOURCES

IMPORTED_VERSION = "catalog-vocab-1"  # model_version of backfilled rows: the vocab.yaml revision that resolved them
# Higher outranks lower: a write never replaces a value from a more trusted source.
SOURCE_RANK = {"imported": 0, "visual_suggestion": 1, "supplier_declared": 2, "staff_approved": 3}


@dataclass(frozen=True)
class Attribute:
    product_id: uuid.UUID
    key: str
    value: str | None  # None = explicitly unknown
    source: str
    variant_id: uuid.UUID | None = None  # None = a product-level attribute
    model_version: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None

    def __post_init__(self):
        if self.key not in ATTRIBUTE_KEYS:
            raise ValueError(f"unknown attribute key {self.key!r}")
        if self.source not in ATTRIBUTE_SOURCES:
            raise ValueError(f"unknown attribute source {self.source!r}")
        if self.value is not None and not 1 <= len(self.value) <= 200:
            raise ValueError("attribute value must be 1-200 characters or None")
        approved = self.approved_by is not None and self.approved_at is not None
        if (self.source == "staff_approved") != approved or (self.approved_by is None) != (self.approved_at is None):
            raise ValueError("exactly staff_approved attributes carry both approved_by and approved_at")


def _only(kind: str, text: str | None, vocab: Vocabulary) -> str | None:
    """The single canonical value of a kind in the text; None when there is none or the text is ambiguous."""
    found = vocab.canonical(kind, text)
    return next(iter(found)) if len(found) == 1 else None


def derive_attributes(product_id: uuid.UUID, material: str | None, variants: list[tuple[uuid.UUID, str | None]],
                      vocab: Vocabulary | None = None) -> list[Attribute]:
    """Imported attributes of one product: fabric from material, color_name per variant. Unresolved stays unknown (None)."""
    vocab = vocab or load_vocabulary()
    rows = [Attribute(product_id, "fabric", _only("material", material, vocab), "imported", model_version=IMPORTED_VERSION)]
    rows += [Attribute(product_id, "color_name", _only("color", color, vocab), "imported", variant_id=vid,
                       model_version=IMPORTED_VERSION) for vid, color in variants]
    return rows
