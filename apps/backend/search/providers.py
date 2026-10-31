"""Embedding provider contract, validation, error classification and a deterministic local fake (no network).

There is deliberately no live adapter and no fallback: an unknown provider name fails closed. A real adapter must
implement EmbeddingProvider, be wired explicitly, and always be called through embed_checked.
"""
import asyncio
import hashlib
import math
import struct
from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable


class EmbeddingError(Exception):
    def __init__(self, message: str, *, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


class RetryableEmbeddingError(EmbeddingError):
    def __init__(self, message: str):
        super().__init__(message, retryable=True)


class NonRetryableEmbeddingError(EmbeddingError):
    def __init__(self, message: str):
        super().__init__(message, retryable=False)


_RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


def classify_status(status: int) -> EmbeddingError:
    """Map a provider HTTP status to an error: throttling, timeouts and 5xx retry; other 4xx never do."""
    cls = RetryableEmbeddingError if status in _RETRYABLE_STATUS else NonRetryableEmbeddingError
    return cls(f"provider returned HTTP {status}")


def classify(exc: BaseException) -> EmbeddingError:
    """Timeouts and connection failures are retryable; everything unknown fails closed as non-retryable."""
    if isinstance(exc, EmbeddingError):
        return exc
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, ConnectionError)):
        return RetryableEmbeddingError(f"{type(exc).__name__}: transient provider failure")
    return NonRetryableEmbeddingError(f"{type(exc).__name__}: provider failure")


@dataclass(frozen=True)
class EmbeddingLimits:
    max_batch: int = 64
    max_chars: int = 4000
    timeout_s: float = 30.0

    def __post_init__(self):
        if self.max_batch < 1 or self.max_chars < 1 or not 0 < self.timeout_s <= 120:
            raise ValueError("embedding limits must be positive and the timeout at most 120s")


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int
    limits: EmbeddingLimits

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def validate_inputs(texts: Sequence[str], limits: EmbeddingLimits) -> None:
    if not texts or len(texts) > limits.max_batch:
        raise NonRetryableEmbeddingError(f"batch must hold 1-{limits.max_batch} texts, got {len(texts)}")
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            raise NonRetryableEmbeddingError("every text must be a non-empty string")
        if len(text) > limits.max_chars:
            raise NonRetryableEmbeddingError(f"text of {len(text)} characters exceeds {limits.max_chars}")


def validate_vectors(vectors, count: int, dimensions: int) -> list[list[float]]:
    """Exactly `count` vectors of exactly `dimensions` finite real numbers; anything else is a non-retryable error."""
    if not isinstance(vectors, (list, tuple)) or len(vectors) != count:
        raise NonRetryableEmbeddingError(f"expected {count} vectors")
    for vec in vectors:
        if not isinstance(vec, (list, tuple)) or len(vec) != dimensions:
            raise NonRetryableEmbeddingError(f"expected vectors of {dimensions} dimensions")
        for x in vec:
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
                raise NonRetryableEmbeddingError("vectors must hold finite numbers only")
    return [[float(x) for x in vec] for vec in vectors]


async def embed_checked(provider: EmbeddingProvider, texts: Sequence[str]) -> list[list[float]]:
    """The only supported way to call a provider: validated input, bounded time, validated and classified output."""
    validate_inputs(texts, provider.limits)
    try:
        vectors = await asyncio.wait_for(provider.embed(list(texts)), provider.limits.timeout_s)
    except Exception as exc:
        raise classify(exc) from exc
    return validate_vectors(vectors, len(texts), provider.dimensions)


class FakeEmbeddingProvider:
    """Hash-derived unit vectors: same text and dimensions always give the same vector. Carries no semantics."""
    name = "fake"
    model = "fake-sha256-v1"

    def __init__(self, dimensions: int = 32, limits: EmbeddingLimits | None = None):
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions
        self.limits = limits or EmbeddingLimits()

    def _vector(self, text: str) -> list[float]:
        raw = b"".join(hashlib.sha256(f"{i}:{text}".encode("utf-8")).digest() for i in range(-(-self.dimensions // 8)))
        vec = [n / 2**31 - 1 for n in struct.unpack(f">{self.dimensions}I", raw[:self.dimensions * 4])]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


def provider_for(name: str, dimensions: int = 32) -> EmbeddingProvider:
    """Only the local fake exists. Any other name fails closed: no live call, no silent fallback to the fake."""
    if name == "fake":
        return FakeEmbeddingProvider(dimensions)
    raise NonRetryableEmbeddingError(f"embedding provider {name!r} is not configured")
