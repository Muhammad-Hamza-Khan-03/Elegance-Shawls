"""Weighted reciprocal rank fusion of a keyword ranking and a semantic ranking. Pure and deterministic.

Weights are normalised to sum to 1 and validated up front (negative, non-finite or all-zero weights are refused,
never silently repaired). Ties on the fused score fall back to newest created_at, then highest id, so the final
order never depends on set/dict iteration or on which list an item came from.
"""
import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

RRF_K = 60  # standard RRF damping constant


@dataclass(frozen=True)
class FusionWeights:
    keyword: float = 0.5
    semantic: float = 0.5

    def __post_init__(self):
        raw = (self.keyword, self.semantic)
        if not all(isinstance(w, (int, float)) and math.isfinite(w) and w >= 0 for w in raw) or sum(raw) <= 0:
            raise ValueError("fusion weights must be finite, non-negative and not both zero")
        total = float(sum(raw))
        object.__setattr__(self, "keyword", self.keyword / total)
        object.__setattr__(self, "semantic", self.semantic / total)


def fuse(keyword: Sequence[uuid.UUID], semantic: Sequence[uuid.UUID], created: dict[uuid.UUID, datetime],
         weights: FusionWeights = FusionWeights()) -> list[uuid.UUID]:
    """Ids best first. Each input is best-first and duplicate-free; `created` maps every id to its created_at."""
    score: dict[uuid.UUID, float] = {}
    for ranking, weight in ((keyword, weights.keyword), (semantic, weights.semantic)):
        if weight == 0:  # a zeroed signal neither ranks nor admits candidates
            continue
        for rank, pid in enumerate(ranking, start=1):
            score[pid] = score.get(pid, 0.0) + weight / (RRF_K + rank)
    # Stable sorts from the least to the most significant key: exact datetimes, no float conversion.
    order = sorted(score, key=lambda pid: pid, reverse=True)
    order.sort(key=lambda pid: created[pid], reverse=True)
    order.sort(key=lambda pid: score[pid], reverse=True)
    return order
