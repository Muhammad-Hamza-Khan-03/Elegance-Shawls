"""Pure hybrid ranking: weights, lexical score, fusion, tie-breaks, paging and ranked cursors."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from repositories.hybrid import _query_vector
from semantic.embeddings import EmbeddingConfig, FakeEmbeddingProvider
from semantic.ranking import Candidate, fuse, lexical_score, normalize_weights, page_after
from utils.pagination import decode_cursor, decode_ranked_cursor, encode_cursor, encode_ranked_cursor

T0 = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
EQUAL = normalize_weights(1, 1)


def uid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def test_weights_are_normalised_and_validated():
    w = normalize_weights(3, 1)
    assert (w.lexical, w.semantic) == (0.75, 0.25)
    for bad in [(0, 0), (-1, 1), (float("nan"), 1), (float("inf"), 1), (True, 1), ("1", 1)]:
        with pytest.raises(ValueError):
            normalize_weights(*bad)


def test_lexical_score_uses_best_field_per_term():
    fields = {"name": "Rose Pashmina", "main_description": "soft wool", "material": "Wool"}
    assert lexical_score(["rose"], fields, []) == 4.0
    assert lexical_score(["wool"], fields, []) == 2.0
    assert lexical_score(["rose", "soft", "zzz"], fields, ["Red"]) == 5.0
    assert lexical_score(["red"], fields, ["Crimson", "Red"]) == 3.0


def test_item_in_both_sources_beats_single_source_items():
    both, lex, sem = (Candidate(uid(1), T0, 4.0, 0.1), Candidate(uid(2), T0, 4.0), Candidate(uid(3), T0, None, 0.05))
    order = [c.id for _, c in fuse([lex, sem, both], EQUAL)]
    assert order[0] == uid(1) and set(order) == {uid(1), uid(2), uid(3)}


def test_weights_change_the_balance():
    lex, sem = Candidate(uid(1), T0, 4.0), Candidate(uid(2), T0, None, 0.1)
    assert [c.id for _, c in fuse([lex, sem], normalize_weights(9, 1))][0] == uid(1)
    assert [c.id for _, c in fuse([lex, sem], normalize_weights(1, 9))][0] == uid(2)


def test_ties_break_on_newest_then_highest_id_regardless_of_input_order():
    cands = [Candidate(uid(1), T0, 4.0), Candidate(uid(2), T0, 4.0), Candidate(uid(3), T0 + timedelta(days=1), 4.0)]
    expected = None
    for perm in (cands, cands[::-1], [cands[1], cands[2], cands[0]]):
        ranked = fuse(perm, EQUAL)
        expected = expected or ranked
        assert ranked == expected
    # Distinct lexical ranks give distinct scores; the newest of the equal-scoring items ranks first in the lexical list.
    assert [c.id for _, c in expected] == [uid(3), uid(2), uid(1)]


def test_equal_fused_scores_across_sources_use_created_at_then_id():
    a, b = Candidate(uid(1), T0, 4.0, None), Candidate(uid(2), T0, None, 0.1)
    # lexical rank 1 and semantic rank 1 contribute equally under equal weights -> a tie on score
    ranked = fuse([a, b], EQUAL)
    assert ranked[0][0] == ranked[1][0] and [c.id for _, c in ranked] == [uid(2), uid(1)]


def test_page_after_is_strict_stable_and_reports_remaining():
    ranked = fuse([Candidate(uid(i), T0 + timedelta(minutes=i), 4.0) for i in range(1, 6)], EQUAL)
    first, more = page_after(ranked, None, 2)
    assert more and len(first) == 2
    pos = (first[-1][0], first[-1][1].created_at, first[-1][1].id)
    second, more = page_after(ranked, pos, 2)
    third, more_after = page_after(ranked, (second[-1][0], second[-1][1].created_at, second[-1][1].id), 2)
    assert more and not more_after
    assert [c.id for _, c in first + second + third] == [c.id for _, c in ranked]


def test_ranked_cursor_round_trip_and_rejections():
    key = (0.0163934426, T0, uid(7))
    cursor = encode_ranked_cursor(key, "bind")
    assert decode_ranked_cursor(cursor, "bind") == key
    with pytest.raises(ValueError):
        decode_ranked_cursor(cursor, "other-binding")
    for bad in ["", "x", cursor[:-1], cursor + "0", cursor.replace(".", "..", 1), "a.b", cursor[::-1]]:
        with pytest.raises(ValueError):
            decode_ranked_cursor(bad, "bind")
    with pytest.raises(ValueError):
        encode_ranked_cursor((float("nan"), T0, uid(1)), "b")


def test_ranked_and_keyset_cursors_are_not_interchangeable():
    with pytest.raises(ValueError):
        decode_cursor(encode_ranked_cursor((0.1, T0, uid(1)), "b"))
    with pytest.raises(ValueError):
        decode_ranked_cursor(encode_cursor(T0, uid(1)), "b")


class _Boom:
    config = EmbeddingConfig("fake", "fake-hash-v1", 64)

    def embed(self, text):
        raise RuntimeError("provider down")


class _WrongDims(_Boom):
    def embed(self, text):
        return [0.1, 0.2]


def test_unavailable_embedder_degrades_to_none():
    assert _query_vector(None, "shawls") is None
    assert _query_vector(_Boom(), "shawls") is None
    assert _query_vector(_WrongDims(), "shawls") is None
    vector, target = _query_vector(FakeEmbeddingProvider(_Boom.config), "shawls")
    assert len(vector) == 64 and target.model == "fake-hash-v1"
