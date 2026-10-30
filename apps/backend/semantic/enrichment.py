"""Staff-facing enrichment suggestions: typed, provenance-carrying, never applied. No I/O, no network, no DB.

A provider proposes values for a product; `suggest()` validates every proposal against the canonical (scrubbed)
input and returns one `FieldSuggestion` per requested field: SUGGESTED (value + source + verbatim evidence),
UNKNOWN (nothing supported it, or the provider output was invalid) or UNSUPPORTED (material/fabric claimed from a
photo, which is never trusted). Every suggestion is `pending_human_review`; the only way forward is `approve()`,
which needs a named staff reviewer and returns an `ApprovedEnrichment` *record*. Writing it to the catalogue,
publishing, or any route is out of scope for this slice and must be a separate reviewed change.
Bump ENRICHMENT_VERSION on any change to the rules below.
(shortcut: only the fake provider is allowlisted; a live provider needs its own reviewed ALLOWED_PROVIDERS entry.)
"""
import hashlib
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

from semantic.representation import RepresentationError, represent
from utils.colour_vocabulary import CANONICAL, SYNONYMS, normalize

ENRICHMENT_VERSION = 1
FIELDS = ("colour", "material", "fabric")
PHOTO_UNSUPPORTED = frozenset({"material", "fabric"})  # cannot be read from a picture; never inferred from one
SOURCES = ("text", "photo")
REVIEW_BELOW = 0.8  # confidence under this always needs staff attention
MAX_PHOTOS = 10
PENDING = "pending_human_review"
ALLOWED_PROVIDERS = {("fake", "fake-enrich-v1")}  # (provider, model); no live provider is selected in this slice

MATERIALS = ("wool", "silk", "cotton", "cashmere", "pashmina", "linen", "viscose", "acrylic")
FABRICS = ("twill", "jacquard", "chiffon", "knit", "woven", "satin", "crepe")


class Outcome(str, Enum):
    SUGGESTED = "suggested"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


class EnrichmentError(ValueError):
    """Bad request, non-allowlisted provider, or approval attempted without a valid human decision."""


@dataclass(frozen=True)
class FieldSuggestion:
    field: str
    outcome: Outcome
    value: str | None
    source: str | None  # text | photo; None for UNKNOWN
    evidence: str | None  # verbatim span of the canonical text, or the photo ref
    confidence: float
    needs_review: bool
    reason: str = ""

    def __post_init__(self):
        if self.field not in FIELDS or not (isinstance(self.confidence, float) and 0.0 <= self.confidence <= 1.0):
            raise EnrichmentError("invalid field or confidence")
        if self.outcome is Outcome.SUGGESTED:
            if not (self.value and self.source in SOURCES and self.evidence):
                raise EnrichmentError("a suggestion needs value, source and evidence")
        elif self.value is not None or self.confidence != 0.0 or not self.needs_review:
            raise EnrichmentError("UNKNOWN/UNSUPPORTED carry no value, zero confidence and need review")
        if self.outcome is Outcome.SUGGESTED and self.confidence < REVIEW_BELOW and not self.needs_review:
            raise EnrichmentError("low confidence must need review")


@dataclass(frozen=True)
class EnrichmentSuggestion:
    provider: str
    model: str
    version: str  # provider/model version string
    enrichment_version: int
    input_hash: str  # sha256 of the canonical input representation (scrubbed text + photo refs)
    fields: tuple[FieldSuggestion, ...]
    status: str = PENDING
    auto_apply: bool = False  # contract constant: nothing is ever applied without approve()

    @property
    def needs_review(self) -> bool:
        return any(f.needs_review for f in self.fields)


@dataclass(frozen=True)
class ApprovedEnrichment:
    """A human decision, as data. Applying it to the catalogue is deliberately not implemented here."""
    input_hash: str
    reviewer: str
    values: tuple[tuple[str, str], ...]  # (field, value) the reviewer accepted


class EnrichmentProvider(Protocol):
    name: str
    model: str
    version: str

    def propose(self, text: str, photos: Sequence[str], fields: Sequence[str]) -> list[dict]: ...


class FakeEnrichmentProvider:
    """Deterministic, offline. Reads the colour/fibre/weave words in the text; for requested fields with no text
    evidence it deliberately guesses from a photo ref, to exercise the service's refusal to trust photo inference."""
    name, model, version = "fake", "fake-enrich-v1", "1"

    def propose(self, text, photos, fields):
        out = []
        for field in fields:
            hit = self._find(field, text)
            if hit:
                out.append({"field": field, "value": hit[0], "source": "text", "evidence": hit[1], "confidence": 0.9})
            elif photos:
                guess = {"colour": "grey", "material": "wool", "fabric": "knit"}[field]
                out.append({"field": field, "value": guess, "source": "photo", "evidence": photos[0], "confidence": 0.95})
        return out

    @staticmethod
    def _find(field, text):
        if field == "colour":
            words = sorted(set(CANONICAL) | set(SYNONYMS), key=lambda w: (-len(w), w))
            for word in words:
                if re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text):
                    return normalize(word), word
            return None
        for word in MATERIALS if field == "material" else FABRICS:
            if re.search(rf"\b{word}\b", text):
                return word, word
        return None


def canonical_input(product: Mapping[str, Any], photos: Sequence[str]) -> tuple[str, str]:
    """(scrubbed text, hash). Photo refs are opaque ids, sorted; raw URLs/paths are not accepted."""
    if not isinstance(photos, (list, tuple)) or len(photos) > MAX_PHOTOS or not all(
            isinstance(p, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", p) for p in photos):
        raise EnrichmentError("photos must be at most 10 opaque ids")
    try:
        rep = represent(product)
    except RepresentationError as exc:
        raise EnrichmentError(str(exc)) from exc
    blob = f"{ENRICHMENT_VERSION}\n{rep['version']}\n{rep['text']}\n" + "\n".join(sorted(set(photos)))
    return rep["text"], hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _unknown(field: str, reason: str) -> FieldSuggestion:
    return FieldSuggestion(field, Outcome.UNKNOWN, None, None, None, 0.0, True, reason)


def _check(field: str, raw: Any, text: str, photos: Sequence[str]) -> FieldSuggestion:
    if not isinstance(raw, Mapping):
        return _unknown(field, "invalid_provider_output")
    source, evidence, value, conf = raw.get("source"), raw.get("evidence"), raw.get("value"), raw.get("confidence")
    if source == "photo" and field in PHOTO_UNSUPPORTED:
        return FieldSuggestion(field, Outcome.UNSUPPORTED, None, None, None, 0.0, True, "photo_inference_unsupported")
    if (source not in SOURCES or not isinstance(value, str) or not value.strip() or isinstance(conf, bool)
            or not isinstance(conf, (int, float)) or not math.isfinite(conf) or not 0 <= conf <= 1):
        return _unknown(field, "invalid_provider_output")
    value = value.strip().casefold()
    if field == "colour" and normalize(value) is None:
        return _unknown(field, "colour_not_in_vocabulary")
    if field == "colour":
        value = normalize(value)
    # Provenance must be real: text evidence is a verbatim span of what was shown to the provider.
    grounded = (evidence in photos) if source == "photo" else (isinstance(evidence, str) and evidence in text)
    if not grounded or not evidence:
        return _unknown(field, "evidence_not_found")
    conf = float(conf)
    return FieldSuggestion(field, Outcome.SUGGESTED, value, source, evidence, conf,
                           conf < REVIEW_BELOW or source == "photo", "")


def suggest(provider: EnrichmentProvider, product: Mapping[str, Any], photos: Sequence[str] = (),
            fields: Sequence[str] = FIELDS) -> EnrichmentSuggestion:
    if (provider.name, provider.model) not in ALLOWED_PROVIDERS:
        raise EnrichmentError("provider is not allowlisted")
    if not fields or len(set(fields)) != len(fields) or any(f not in FIELDS for f in fields):
        raise EnrichmentError("fields must be a non-empty, unique subset of " + ", ".join(FIELDS))
    text, digest = canonical_input(product, photos)
    try:
        raw = provider.propose(text, tuple(photos), tuple(fields))
    except Exception:  # a failing provider degrades to UNKNOWN, never to a guess
        raw = None
    by_field = {r.get("field"): r for r in raw if isinstance(r, Mapping)} if isinstance(raw, list) else {}
    results = tuple(_check(f, by_field[f], text, photos) if f in by_field else
                    _unknown(f, "no_supported_evidence" if raw is not None else "provider_failed") for f in fields)
    return EnrichmentSuggestion(provider.name, provider.model, provider.version, ENRICHMENT_VERSION, digest, results)


def approve(suggestion: EnrichmentSuggestion, reviewer: str, accept: Sequence[str]) -> ApprovedEnrichment:
    """The human boundary. Only SUGGESTED fields can be accepted, only by a named reviewer."""
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise EnrichmentError("a named staff reviewer is required")
    by_field = {f.field: f for f in suggestion.fields}
    if not accept or any(a not in by_field or by_field[a].outcome is not Outcome.SUGGESTED for a in accept):
        raise EnrichmentError("only suggested fields can be approved")
    return ApprovedEnrichment(suggestion.input_hash, reviewer.strip(),
                              tuple((a, by_field[a].value) for a in dict.fromkeys(accept)))
