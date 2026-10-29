"""The enrichment output contract: allowed fields, canonical vocabularies and strict validation.

A response is accepted only when it has exactly the contract fields, each as {"value", "reason"}. Categorical values
must be canonical vocabulary; a field the model cannot support is null with a reason. Anything else (extra or factual
fields such as fabric/price/stock, out-of-vocabulary values, unsafe free text) rejects the whole response.
"""
import hashlib
import json
import re
from dataclasses import dataclass

from catalog.query import load_vocabulary

VOCABULARY_VERSION = "enrichment-vocab-1"
SOURCE = "visual_suggestion"
MAX_ATTEMPTS = 2

# color_name is the reviewed catalogue colour vocabulary (vocab.yaml); the rest are reviewed here, with the version above.
CATEGORICAL: dict[str, frozenset[str]] = {
    "color_family": frozenset({"neutral", "warm", "cool", "earth", "bright", "pastel", "dark"}),
    "pattern": frozenset({"solid", "striped", "checked", "floral", "paisley", "geometric", "embroidered", "printed"}),
    "occasion": frozenset({"everyday", "formal", "wedding", "festive", "travel"}),
    "season": frozenset({"winter", "summer", "all_season"}),
    "style": frozenset({"classic", "modern", "traditional", "minimal", "statement"}),
}
FREE_TEXT: dict[str, int] = {"description": 600, "seo_title": 70, "seo_description": 160}
FIELDS = ("color_family", "color_name", "pattern", "occasion", "season", "style", *FREE_TEXT)
MAX_REASON = 200
PROHIBITED = frozenset({"fabric", "composition", "authenticity", "price", "stock", "availability", "material", "currency"})

_TAGS = re.compile(r"<[^>]*>")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
# shortcut: keyword heuristic for factual claims (price/stock/authenticity); replace with a reviewed classifier if it misfires.
_CLAIM = re.compile(r"\b(authentic|genuine|original|certified|pure|handmade|in stock|out of stock|sold out|available|"
                    r"price[sd]?|discount|sale|rs\.?|pkr|usd)\b|\d\s*%|[$€£]", re.IGNORECASE)


def allowed_values(field: str) -> frozenset[str]:
    if field == "color_name":
        return frozenset(v for kind, v in load_vocabulary().terms.values() if kind == "color")
    return CATEGORICAL[field]


def input_hash(payload: dict) -> str:
    canonical = json.dumps({"input": payload, "vocabulary": VOCABULARY_VERSION}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def sanitize(text: str, limit: int) -> str:
    """Strip markup and control characters, collapse whitespace, cap at limit (at a word boundary)."""
    text = " ".join(_CONTROL.sub(" ", _TAGS.sub(" ", text)).split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-") or text[:limit]


@dataclass(frozen=True)
class Parsed:
    suggestions: dict | None
    errors: list[str]


def parse_response(raw: str, source_text: str = "") -> Parsed:
    """Strictly validate the provider text. Errors name fields and rules, never echo model output."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except ValueError:
        return Parsed(None, ["response is not valid JSON"])
    if not isinstance(data, dict):
        return Parsed(None, ["response must be a JSON object"])
    extra = [key for key in data if key not in FIELDS]
    errors = [f"unexpected fields: {len(extra)}"] if extra else []  # counted, never echoed
    errors += [f"prohibited factual field: {key}" for key in extra if key in PROHIBITED]
    errors +=[f"missing field: {key}" for key in FIELDS if key not in data]
    vocab = load_vocabulary()
    source_materials = vocab.canonical("material", source_text)
    out: dict = {}
    for field in FIELDS:
        if field not in data:
            continue
        entry = data[field]
        if not isinstance(entry, dict) or set(entry) != {"value", "reason"}:
            errors.append(f"{field}: must be an object with exactly value and reason")
            continue
        value, reason = entry["value"], entry["reason"]
        if reason is not None and not isinstance(reason, str):
            errors.append(f"{field}: reason must be text or null")
            continue
        reason = sanitize(reason, MAX_REASON) if reason else None
        if value is None:
            if not reason:
                errors.append(f"{field}: null value needs a reason")
                continue
        elif not isinstance(value, str):
            errors.append(f"{field}: value must be text or null")
            continue
        elif field in FREE_TEXT:
            value = sanitize(value, FREE_TEXT[field])
            if not value:
                errors.append(f"{field}: empty after sanitising")
                continue
            if _CLAIM.search(value) or vocab.canonical("material", value) - source_materials:
                errors.append(f"{field}: contains a factual claim (price, stock, authenticity or fabric)")
                continue
        elif value not in allowed_values(field):
            errors.append(f"{field}: value is not in the canonical vocabulary")
            continue
        out[field] = {"value": value, "reason": reason, "source": SOURCE}
    return Parsed(None if errors else out, errors)
