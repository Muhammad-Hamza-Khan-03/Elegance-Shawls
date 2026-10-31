"""P1-S4a: embedding provider contract, validation, failure classification and the offline fake (no network)."""
import asyncio
import math
import socket

import pytest

from search import providers
from search.providers import (EmbeddingLimits, EmbeddingProvider, FakeEmbeddingProvider, NonRetryableEmbeddingError,
                              RetryableEmbeddingError, classify, classify_status, embed_checked, provider_for,
                              validate_inputs, validate_vectors)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


def run(coro):
    return asyncio.run(coro)


class Stub:
    name, model, dimensions = "stub", "stub-1", 3

    def __init__(self, result=None, exc=None, delay=0.0, limits=None):
        self.result, self.exc, self.delay, self.limits = result, exc, delay, limits or EmbeddingLimits(timeout_s=0.2)

    async def embed(self, texts):
        await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return self.result if self.result is not None else [[0.1, 0.2, 0.3] for _ in texts]


def test_fake_is_deterministic_unit_length_and_dimension_exact():
    fake = FakeEmbeddingProvider(dimensions=24)
    assert isinstance(fake, EmbeddingProvider)
    a, b = run(embed_checked(fake, ["brown shawl", "بھورا شال"])), run(embed_checked(FakeEmbeddingProvider(24), ["brown shawl", "بھورا شال"]))
    assert a == b and a[0] != a[1] and all(len(v) == 24 for v in a)
    assert all(math.isclose(math.sqrt(sum(x * x for x in v)), 1.0) for v in a)
    assert run(embed_checked(fake, ["brown shawl"]))[0] == a[0]  # batch position does not matter
    with pytest.raises(ValueError):
        FakeEmbeddingProvider(0)


def test_fake_vector_snapshot_is_pinned():
    assert [round(x, 6) for x in FakeEmbeddingProvider(4)._vector("shawl")] == [0.65754, 0.59177, 0.316171, -0.34276]
    assert FakeEmbeddingProvider(4)._vector("shawl") != FakeEmbeddingProvider(4)._vector("shawl ")


def test_input_validation_bounds_batch_length_and_blank_text():
    limits = EmbeddingLimits(max_batch=2, max_chars=5)
    validate_inputs(["a", "12345"], limits)
    for bad in ([], ["a", "b", "c"], [""], ["   "], ["123456"], [None], [5]):
        with pytest.raises(NonRetryableEmbeddingError):
            validate_inputs(bad, limits)
    for kwargs in ({"max_batch": 0}, {"max_chars": 0}, {"timeout_s": 0}, {"timeout_s": 500}):
        with pytest.raises(ValueError):
            EmbeddingLimits(**kwargs)


@pytest.mark.parametrize("vectors", [
    [], [[0.1, 0.2, 0.3]], [[0.1, 0.2], [0.1, 0.2]], [[0.1, 0.2, 0.3, 0.4], [0, 0, 0]], [[], []],
    [[0.1, float("nan"), 0.3], [0, 0, 0]], [[0.1, float("inf"), 0.3], [0, 0, 0]], [[0.1, float("-inf"), 0.3], [0, 0, 0]],
    [[0.1, "x", 0.3], [0, 0, 0]], [[0.1, None, 0.3], [0, 0, 0]], [[True, 0, 0], [0, 0, 0]], "ab", None,
])
def test_vector_validation_rejects_wrong_count_dimension_and_non_finite(vectors):
    with pytest.raises(NonRetryableEmbeddingError) as err:
        validate_vectors(vectors, 2, 3)
    assert err.value.retryable is False


def test_vector_validation_accepts_exact_finite_numbers_and_coerces_to_float():
    out = validate_vectors([(1, 0, -1), [0.5, 0.25, 0.125]], 2, 3)
    assert out == [[1.0, 0.0, -1.0], [0.5, 0.25, 0.125]] and all(type(x) is float for v in out for x in v)


def test_embed_checked_rejects_bad_provider_output_and_bad_input_before_calling():
    with pytest.raises(NonRetryableEmbeddingError):
        run(embed_checked(Stub(result=[[0.1, math.nan, 0.3]]), ["a"]))
    with pytest.raises(NonRetryableEmbeddingError):
        run(embed_checked(Stub(result=[[0.1, 0.2]]), ["a"]))
    called = Stub(exc=AssertionError("must not be called"))
    with pytest.raises(NonRetryableEmbeddingError):
        run(embed_checked(called, []))
    assert run(embed_checked(Stub(), ["a", "b"])) == [[0.1, 0.2, 0.3]] * 2


@pytest.mark.parametrize("exc, retryable", [
    (TimeoutError(), True), (ConnectionResetError(), True), (asyncio.TimeoutError(), True),
    (RetryableEmbeddingError("x"), True), (NonRetryableEmbeddingError("x"), False),
    (ValueError("bad"), False), (KeyError("k"), False), (RuntimeError("???"), False),
])
def test_failures_are_classified_and_unknown_errors_fail_closed(exc, retryable):
    with pytest.raises(providers.EmbeddingError) as err:
        run(embed_checked(Stub(exc=exc), ["a"]))
    assert err.value.retryable is retryable


def test_slow_provider_times_out_as_retryable():
    with pytest.raises(RetryableEmbeddingError):
        run(embed_checked(Stub(delay=1.0, limits=EmbeddingLimits(timeout_s=0.05)), ["a"]))


def test_http_status_classification():
    for status in (408, 409, 425, 429, 500, 502, 503, 504):
        assert classify_status(status).retryable is True
    for status in (400, 401, 403, 404, 422):
        assert classify_status(status).retryable is False
    assert classify(RuntimeError("x")).retryable is False


def test_no_live_provider_and_no_silent_fallback():
    assert isinstance(provider_for("fake"), FakeEmbeddingProvider)
    for name in ("openai", "openai-compatible", "", "FAKE", "default"):
        with pytest.raises(NonRetryableEmbeddingError):
            provider_for(name)
    source = open(providers.__file__, encoding="utf-8").read()
    for forbidden in ("import httpx", "import requests", "import openai", "urllib", "import socket", "os.environ", "getenv"):
        assert forbidden not in source
