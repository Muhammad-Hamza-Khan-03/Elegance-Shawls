"""Deterministic Urdu/Roman Urdu parsing; deliberately not an ASR implementation."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .contract import VoiceOutcome

_URDU_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_TRANSLITERATIONS = {
    "rupay": "pkr", "rupee": "pkr", "rupees": "pkr", "rs": "pkr", "رپے": "pkr", "روپے": "pkr",
    "chahiye": "want", "chaheye": "want", "چاہیے": "want", "نہیں": "nahi", "نہ": "nahi",
    "nahin": "nahi", "nahi": "nahi", "mat": "nahi", "نہیں چاہیے": "nahi want",
}
_NEGATION = re.compile(r"(?:^|\s)(?:nahi|نہیں|نہ|mat)(?:\s|$)")
_PRICE = re.compile(r"(?:(?:pkr|rs|rupees?|rupay|روپے|رپے)\s*)?(\d{1,3}(?:[,_]\d{3})+|\d{3,6})(?:\s*(?:pkr|rs|rupees?|rupay|روپے|رپے))?", re.I)


@dataclass(frozen=True)
class ParsedIntent:
    normalized_transcript: str
    price_pkr: int | None
    negated: bool | None
    outcome: VoiceOutcome
    confidence: float
    needs_review: bool


def normalize_transcript(transcript: str) -> str:
    text = transcript.translate(_URDU_DIGITS).lower()
    # Numeric Urdu punctuation is a thousands separator; other punctuation is spacing.
    text = re.sub(r"(?<=\d)[،,](?=\d)", "", text)
    text = re.sub(r"[،,؛;]", " ", text)
    for source, target in sorted(_TRANSLITERATIONS.items(), key=lambda item: -len(item[0])):
        text = re.sub(rf"(?<!\w){re.escape(source)}(?!\w)", target, text)
    return " ".join(text.split())


def parse_intent(normalized: str) -> ParsedIntent:
    prices = [int(match.replace(",", "").replace("_", "")) for match in _PRICE.findall(normalized)]
    negated = bool(_NEGATION.search(normalized))
    if len(set(prices)) > 1:
        return ParsedIntent(normalized, None, None, VoiceOutcome.AMBIGUOUS, 0.2, True)
    price = prices[0] if prices else None
    if not normalized.strip():
        return ParsedIntent(normalized, None, None, VoiceOutcome.UNCERTAIN, 0.0, True)
    if price is None and len(normalized.split()) < 2:
        return ParsedIntent(normalized, None, None, VoiceOutcome.UNCERTAIN, 0.35, True)
    confidence = 0.96 if price is not None else 0.72
    return ParsedIntent(normalized, price, negated, VoiceOutcome.NEGATED if negated else VoiceOutcome.ACCEPTED, confidence, confidence < 0.8)
