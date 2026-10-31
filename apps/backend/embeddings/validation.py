"""Strict input/output validation. Nothing is repaired, coerced, truncated or normalised: a bad value raises."""
import math
from typing import Sequence

from .provider import EmbeddingLimits, InputError, MalformedResponseError


def validate_inputs(texts: Sequence[str], limits: EmbeddingLimits) -> None:
    if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence):
        raise InputError("texts must be a sequence of strings")
    if not texts or len(texts) > limits.max_batch:
        raise InputError(f"batch must hold 1-{limits.max_batch} texts")
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            raise InputError("every text must be a non-empty string")
        if len(text) > limits.max_chars:
            raise InputError(f"a text exceeds {limits.max_chars} characters")


def validate_vectors(vectors: object, count: int, dimension: int) -> list[list[float]]:
    """Exactly `count` vectors, each exactly `dimension` finite int/float values (bool rejected). Returned unchanged."""
    if not isinstance(vectors, list) or len(vectors) != count:
        raise MalformedResponseError("vector count does not match input count")
    for vector in vectors:
        if not isinstance(vector, list) or len(vector) != dimension:
            raise MalformedResponseError("vector dimension does not match the expected dimension")
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise MalformedResponseError("vector holds a non-finite or non-numeric value")
    return vectors
