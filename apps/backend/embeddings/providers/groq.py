"""Groq adapter: fails closed. No Groq embeddings model is verified for this gate, so nothing is ever sent.

Never substitute chat completions or another model. To enable, add a model to EMBEDDING_CAPABLE_MODELS only after
confirming Groq's embeddings endpoint serves it, and implement the explicit request mapping here.
"""
from ..config import EvalConfig
from ..provider import UnsupportedProviderError

EMBEDDING_CAPABLE_MODELS: frozenset[str] = frozenset()


class GroqEmbeddingProvider:
    provider = "groq"

    def __init__(self, config: EvalConfig, *_, **__):
        if config.model not in EMBEDDING_CAPABLE_MODELS:
            raise UnsupportedProviderError("groq model is not verified to support embeddings")
        raise UnsupportedProviderError("groq embeddings request mapping is not implemented")
