"""Strict embedding validation: no repair, no normalisation."""
import math

import pytest

from embeddings.provider import EmbeddingLimits, InputError, MalformedResponseError
from embeddings.validation import validate_inputs, validate_vectors


def test_valid_vectors_returned_unchanged():
    vectors = [[1, 2.5, -3.0], [0, 0, 0]]
    assert validate_vectors(vectors, 2, 3) is vectors
    assert vectors == [[1, 2.5, -3.0], [0, 0, 0]]  # ints not coerced, nothing normalised


@pytest.mark.parametrize("vectors,count,dim", [
    ([[1.0, 2.0]], 2, 2),  # too few
    ([[1.0, 2.0]] * 3, 2, 2),  # too many
    ([], 1, 2),
    ([[1.0]], 1, 2),  # short
    ([[1.0, 2.0, 3.0]], 1, 2),  # long
    ([[1.0, 2.0], [1.0, 2.0, 3.0]], 2, 2),  # unstable dimension across items
    ([[]], 1, 2),
    ([[float("nan"), 1.0]], 1, 2),
    ([[float("inf"), 1.0]], 1, 2),
    ([[1.0, -math.inf]], 1, 2),
    ([[True, 1.0]], 1, 2),
    ([[False, 1.0]], 1, 2),
    ([["1", 2.0]], 1, 2),
    ([[None, 2.0]], 1, 2),
    ([[1.0, [2.0]]], 1, 2),
    ([(1.0, 2.0)], 1, 2),  # tuple, not a JSON array
    ([{"values": [1.0, 2.0]}], 1, 2),
    ("ab", 2, 1),
    (None, 1, 1),
    ({"a": 1}, 1, 1),
])
def test_malformed_vectors_rejected(vectors, count, dim):
    with pytest.raises(MalformedResponseError):
        validate_vectors(vectors, count, dim)


LIMITS = EmbeddingLimits(max_batch=2, max_chars=5)


def test_valid_inputs_pass():
    validate_inputs(["a", "abcde"], LIMITS)
    validate_inputs(("a",), LIMITS)


@pytest.mark.parametrize("texts", [[], ["a", "b", "c"], [""], ["   "], ["abcdef"], [1], [None], ["a", None], "abc",
                                   b"abc", None, 5])
def test_bad_inputs_rejected(texts):
    with pytest.raises(InputError):
        validate_inputs(texts, LIMITS)


def test_input_errors_do_not_echo_text():
    with pytest.raises(InputError) as exc:
        validate_inputs(["secret-catalogue-text"], LIMITS)
    assert "secret-catalogue-text" not in str(exc.value)
