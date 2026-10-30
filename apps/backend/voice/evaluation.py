"""Exact M5-S1 scoring and fail-closed release gate."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .normalization import normalize_transcript, parse_intent


@dataclass(frozen=True)
class EvaluationResult:
    examples: int
    price_accuracy: float
    negation_accuracy: float
    score: float
    passed: bool
    wer_used: bool = False


@dataclass(frozen=True)
class GateResult:
    ready: bool
    reason: str


def evaluate_cases(cases: Iterable[dict]) -> EvaluationResult:
    rows = list(cases)
    if not rows:
        return EvaluationResult(0, 0.0, 0.0, 0.0, False)
    price_hits = negation_hits = 0
    for row in rows:
        parsed = parse_intent(normalize_transcript(row["transcript"]))
        price_hits += parsed.price_pkr == row.get("expected_price_pkr")
        negation_hits += parsed.negated == row.get("expected_negated")
    price = price_hits / len(rows)
    negation = negation_hits / len(rows)
    score = (price + negation) / 2
    return EvaluationResult(len(rows), price, negation, score, score == 1.0)


def release_gate(records: Iterable[dict]) -> GateResult:
    rows = list(records)
    if not rows:
        return GateResult(False, "empty evaluation")
    if not all(row.get("reviewed") is True for row in rows):
        return GateResult(False, "unreviewed evaluation")
    if not all(row.get("passed") is True for row in rows):
        return GateResult(False, "failed evaluation")
    return GateResult(True, "reviewed evaluation passed")
