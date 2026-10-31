"""Embedding provider boundary: allowlist, fail-closed config, vector validation, test-only fake provider.

Nothing here performs network I/O. Real providers are added by extending ALLOWED_MODELS in a reviewed change;
the fake needs an explicit test opt-in.
"""
import hashlib
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

# (provider, model) -> dimensions. local_e5 is the evaluated choice (semantic/local_e5.py); the fake is test-only.
ALLOWED_MODELS: dict[tuple[str, str], int] = {("fake", "fake-hash-v1"): 64, ("local_e5", "intfloat/multilingual-e5-base"): 768}
TEST_ONLY_PROVIDERS = frozenset({"fake"})


class EmbeddingConfigError(ValueError):
    """Configuration is invalid or not allowlisted; semantic search must stay disabled."""


class VectorError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    model: str
    dimensions: int


def load_config(env: Mapping[str, str], *, allow_test_providers: bool = False) -> EmbeddingConfig | None:
    """None means disabled (nothing configured). Anything configured but wrong raises, never degrades to a guess."""
    provider = (env.get("SEMANTIC_EMBEDDING_PROVIDER") or "").strip().lower()
    model = (env.get("SEMANTIC_EMBEDDING_MODEL") or "").strip()
    raw_dims = (env.get("SEMANTIC_EMBEDDING_DIMENSIONS") or "").strip()
    if not (provider or model or raw_dims):
        return None
    expected = ALLOWED_MODELS.get((provider, model))
    if expected is None:
        raise EmbeddingConfigError(f"embedding model {provider!r}/{model!r} is not allowlisted")
    if provider in TEST_ONLY_PROVIDERS and not allow_test_providers:
        raise EmbeddingConfigError(f"provider {provider!r} is for tests only")
    if not raw_dims.isdigit() or int(raw_dims) != expected:
        raise EmbeddingConfigError(f"dimensions must be exactly {expected} for {provider}/{model}")
    return EmbeddingConfig(provider, model, expected)


def validate_vector(vector: Sequence[float], dimensions: int) -> tuple[float, ...]:
    if isinstance(vector, (str, bytes)) or not isinstance(vector, Sequence):
        raise VectorError("not_a_sequence")
    if len(vector) != dimensions:
        raise VectorError("wrong_dimension", f"expected {dimensions}, got {len(vector)}")
    for i, x in enumerate(vector):
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise VectorError("non_numeric", f"index {i}")
        if not math.isfinite(x):
            raise VectorError("non_finite", f"index {i}")
    return tuple(float(x) for x in vector)


class FakeEmbeddingProvider:
    """Hashed bag-of-tokens, L2-normalised. Stable across processes (SHA-256, no hash() / randomness)."""

    def __init__(self, config: EmbeddingConfig):
        if config.provider != "fake" or ALLOWED_MODELS.get((config.provider, config.model)) != config.dimensions:
            raise EmbeddingConfigError("FakeEmbeddingProvider needs the allowlisted fake config")
        self.config = config

    def embed(self, text: str) -> tuple[float, ...]:
        dims = self.config.dimensions
        acc = [0.0] * dims
        for token in text.split():
            stream = hashlib.shake_256(f"{self.config.model}|{token}".encode("utf-8")).digest(dims)
            for i, byte in enumerate(stream):
                acc[i] += byte - 127.5
        norm = math.sqrt(sum(x * x for x in acc))
        return validate_vector([x / norm if norm else 0.0 for x in acc], dims)
