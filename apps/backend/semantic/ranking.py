"""Pure, deterministic hybrid ranking: lexical score, weighted reciprocal-rank fusion and total ordering.

No I/O. Same inputs always give the same order: ties on the fused score fall back to newest created_at, then
highest id, so a position (score, created_at, id) is unique and usable as a keyset cursor.
"""
import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

RRF_K = 60  # standard reciprocal-rank constant; larger flattens the head of each list
SCORE_DIGITS = 12  # scores are rounded so they survive a cursor round trip bit-for-bit
# Best field a search term hits decides its weight (name beats description).
FIELD_WEIGHTS = {"name": 4.0, "item_number": 3.0, "slug": 3.0, "variant": 3.0, "material": 2.0, "main_description": 1.0}


@dataclass(frozen=True)
class Weights:
    lexical: float
    semantic: float


@dataclass(frozen=True)
class Candidate:
    id: uuid.UUID
    created_at: datetime
    lexical: float | None = None  # None: not a lexical match
    distance: float | None = None  # None: not a semantic hit (cosine distance, smaller is closer)


def normalize_weights(lexical: float, semantic: float) -> Weights:
    """Non-negative, finite, not both zero; scaled to sum to 1."""
    for w in (lexical, semantic):
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w) or w < 0:
            raise ValueError("fusion weights must be finite and non-negative")
    top = max(lexical, semantic)
    if top <= 0:
        raise ValueError("fusion weights must not both be zero")
    # Scale by the larger weight first so lexical + semantic cannot overflow (e.g. 1.7e308 twice).
    lexical, semantic = lexical / top, semantic / top
    total = lexical + semantic
    return Weights(lexical / total, semantic / total)


def lexical_score(terms: Sequence[str], fields: Mapping[str, str | None], variant_texts: Sequence[str | None]) -> float:
    """Sum over terms of the weight of the best field containing it (case-insensitive substring)."""
    haystacks = {name: (fields.get(name) or "").casefold() for name in FIELD_WEIGHTS if name != "variant"}
    haystacks["variant"] = "\n".join((t or "").casefold() for t in variant_texts)
    total = 0.0
    for term in terms:
        t = term.casefold()
        total += max((w for name, w in FIELD_WEIGHTS.items() if t in haystacks[name]), default=0.0)
    return total


def fuse(candidates: Sequence[Candidate], weights: Weights) -> list[tuple[float, Candidate]]:
    """Weighted reciprocal-rank fusion, best first. Ranks inside each source are themselves tie-broken
    deterministically (lexical: score, created_at, id desc; semantic: distance, id asc)."""
    lex = sorted((c for c in candidates if c.lexical is not None), key=lambda c: (c.lexical, c.created_at, c.id), reverse=True)
    sem = sorted((c for c in candidates if c.distance is not None), key=lambda c: (round(c.distance, 9), c.id))
    score: dict[uuid.UUID, float] = {}
    for rank, c in enumerate(lex, 1):
        score[c.id] = score.get(c.id, 0.0) + weights.lexical / (RRF_K + rank)
    for rank, c in enumerate(sem, 1):
        score[c.id] = score.get(c.id, 0.0) + weights.semantic / (RRF_K + rank)
    by_id = {c.id: c for c in candidates}
    ranked = [(round(s, SCORE_DIGITS), by_id[i]) for i, s in score.items()]
    return sorted(ranked, key=lambda r: (r[0], r[1].created_at, r[1].id), reverse=True)


def page_after(ranked: Sequence[tuple[float, Candidate]], after: tuple[float, datetime, uuid.UUID] | None,
               limit: int) -> tuple[list[tuple[float, Candidate]], bool]:
    """Items strictly after `after` in ranking order, at most `limit`, and whether more remain."""
    rest = [r for r in ranked if after is None or (r[0], r[1].created_at, r[1].id) < after]
    return rest[:limit], len(rest) > limit
