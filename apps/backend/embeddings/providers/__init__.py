from ..config import EvalConfig
from ..provider import EmbeddingLimits, EmbeddingProvider, UnsupportedProviderError
from .gemini import GeminiEmbeddingProvider
from .groq import GroqEmbeddingProvider

_ADAPTERS = {"gemini": GeminiEmbeddingProvider, "groq": GroqEmbeddingProvider}


def build_provider(config: EvalConfig, dimension: int, limits: EmbeddingLimits | None = None,
                   transport=None) -> EmbeddingProvider:
    """Exactly the configured provider; an unknown name fails closed and nothing falls back."""
    adapter = _ADAPTERS.get(config.provider)
    if adapter is None:
        raise UnsupportedProviderError("unknown embedding provider")
    return adapter(config, dimension, limits, transport)
