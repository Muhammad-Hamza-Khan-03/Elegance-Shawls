"""Container-free: fusion weights, deterministic tie-breaks and offset-cursor integrity."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from semantic.fusion import FusionWeights, fuse

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def ids(n):
    return [uuid.UUID(int=i + 1) for i in range(n)]


def test_weights_are_normalised_and_invalid_ones_refused():
    w = FusionWeights(3, 1)
    assert (w.keyword, w.semantic) == (0.75, 0.25)
    for bad in [(0, 0), (-1, 1), (float("nan"), 1), (float("inf"), 1), ("a", 1)]:
        with pytest.raises(ValueError):
            FusionWeights(*bad)


def test_fusion_rewards_agreement_and_respects_weights():
    a, b, c = ids(3)
    created = {i: T0 for i in (a, b, c)}
    assert fuse([a, b], [b, c], created) == [b, a, c]                       # b is in both lists
    assert fuse([a, b], [b, c], created, FusionWeights(1, 0)) == [a, b]      # zeroed signal admits nobody
    assert fuse([a, b], [b, c], created, FusionWeights(0, 1)) == [b, c]
    assert fuse([a], [b], created, FusionWeights(9, 1)) == [a, b]


def test_ties_break_on_newest_created_at_then_highest_id_regardless_of_input_order():
    a, b, c = ids(3)
    created = {a: T0, b: T0 + timedelta(days=1), c: T0 + timedelta(days=1)}
    # a, b, c all rank first in exactly one list at equal weight pairs -> equal scores
    for kw, sem in (([a, b], [c]), ([c], [a, b]), ([b, c], [a])):
        out = fuse([kw[0]], [sem[0]], created)
        assert out == sorted(out, key=lambda p: (created[p], p), reverse=True)
    assert fuse([a], [b], created) == [b, a]
    assert fuse([b], [c], created) == [c, b]   # same created_at: higher id first
