"""Local-only bridge from the offline multilingual-e5 provider to the search provider contract. Never for production.

Gated three ways: LOCAL_SEMANTIC_SEARCH_ENABLED (default off), a local-looking ENVIRONMENT (production/staging and any
unknown name are refused), and an explicit model directory plus pinned revision. Failure is a typed EmbeddingError, which
the search path turns into lexical-only results. Queries use the e5 "query: " prefix; indexing needs kind="passage".
"""
import asyncio
from typing import Sequence

from configuration.config import settings
from embeddings.config import EvalConfig
from embeddings.provider import EmbeddingEvalError
from embeddings.providers.local_e5 import DIMENSION, MODEL, LocalE5EmbeddingProvider
from search.providers import EmbeddingLimits, EmbeddingProvider, NonRetryableEmbeddingError

# Staging is explicitly opt-in for the isolated E5 rehearsal. Production and unknown
# environments remain refused; the staging image carries the pinned model offline.
LOCAL_ENVIRONMENTS = frozenset({"development", "dev", "local", "test", "staging"})
_loaded: dict[tuple[str, str], LocalE5EmbeddingProvider] = {}   # one model load per process; failures are not cached


class LocalE5Adapter:
    name = "local_e5"
    model = MODEL
    dimensions = DIMENSION

    def __init__(self, inner: LocalE5EmbeddingProvider, kind: str):
        self._inner, self._kind = inner, kind
        self.model_revision = inner.revision
        self.limits = EmbeddingLimits(max_chars=4000, timeout_s=inner.limits.timeout_s)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            return (await asyncio.to_thread(self._inner.embed, list(texts), kind=self._kind)).vectors
        except EmbeddingEvalError:
            raise NonRetryableEmbeddingError("local embedding failed") from None


def local_provider(kind: str = "query") -> EmbeddingProvider:
    """The pinned local provider, or NonRetryableEmbeddingError when the flag, environment or model settings refuse it."""
    if not settings.local_semantic_search_enabled:
        raise NonRetryableEmbeddingError("local semantic search is disabled")
    if settings.environment.strip().lower() not in LOCAL_ENVIRONMENTS:
        raise NonRetryableEmbeddingError("local semantic search is refused outside a local environment")
    path, revision = settings.local_e5_model_path, settings.local_e5_model_revision
    try:
        inner = _loaded.get((path, revision))
        if inner is None:
            options = {"model_path": path, "revision": revision}
            inner = _loaded[(path, revision)] = LocalE5EmbeddingProvider(EvalConfig("local_e5", MODEL, ""), DIMENSION, None, options)
    except EmbeddingEvalError:
        raise NonRetryableEmbeddingError("local e5 model is unavailable") from None
    return LocalE5Adapter(inner, kind)
