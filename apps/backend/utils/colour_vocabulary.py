"""Controlled colour vocabulary. Bump VOCABULARY_VERSION on any change to CANONICAL or SYNONYMS."""
from dataclasses import dataclass

VOCABULARY_VERSION = 1

CANONICAL = ("beige", "black", "blue", "brown", "burgundy", "camel", "cream", "green", "grey",
             "ivory", "maroon", "multicolour", "navy", "orange", "pink", "purple", "red", "white", "yellow")

# alias -> canonical; only unambiguous spellings. Anything else stays unknown (never guessed).
SYNONYMS = {
    "gray": "grey", "charcoal": "grey", "multicolor": "multicolour", "multi": "multicolour",
    "multi-colour": "multicolour", "multi colour": "multicolour", "off white": "ivory", "off-white": "ivory",
    "wine": "burgundy", "navy blue": "navy", "tan": "camel", "violet": "purple",
}

# Precedence, strongest first: an explicit variant colour always wins; the variant name is only
# consulted when the colour is absent, and never overrides one (even an unrecognised one).
SOURCES = ("variant_color", "variant_name")


def normalize(value: str | None) -> str | None:
    """Canonical colour for a free-text value, or None when null/blank/unknown."""
    key = " ".join((value or "").lower().split())
    if key in CANONICAL:
        return key
    return SYNONYMS.get(key)


@dataclass(frozen=True)
class ResolvedColour:
    canonical: str | None
    source: str | None
    version: int = VOCABULARY_VERSION


def resolve(color: str | None, name: str | None = None) -> ResolvedColour:
    if (color or "").strip():
        found = normalize(color)
        return ResolvedColour(found, SOURCES[0] if found else None)
    found = normalize(name)
    return ResolvedColour(found, SOURCES[1] if found else None)


def spellings(canonical: str) -> list[str]:
    """Every lowercase, single-spaced raw value that normalizes to `canonical`."""
    if canonical not in CANONICAL:
        raise ValueError(f"unknown colour: {canonical}")
    return [canonical, *(a for a, c in SYNONYMS.items() if c == canonical)]
