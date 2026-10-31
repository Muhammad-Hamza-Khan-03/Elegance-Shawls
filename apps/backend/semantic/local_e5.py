"""Local multilingual-e5-base embedder: CPU, offline, one pinned model (chosen by the recorded synthetic eval, recall@10 0.954,
Roman Urdu 0.892; see docs/qa/local-e5-evaluation-manifest.md on ai/local-e5-v2-evidence). No download happens here.

Fetch the weights once (`scripts/fetch_e5_model.py`), then set SEMANTIC_EMBEDDING_PROVIDER=local_e5,
SEMANTIC_EMBEDDING_MODEL=intfloat/multilingual-e5-base, SEMANTIC_EMBEDDING_DIMENSIONS=768 and SEMANTIC_E5_MODEL_PATH=<dir>.
Anything missing or wrong disables semantic search (keyword search keeps working); it never blocks startup.
(shortcut: embed() runs on the request thread, ~tens of ms on CPU; move to a thread pool when traffic needs it.)
"""
import logging
import os
from functools import lru_cache

from semantic.embeddings import EmbeddingConfig, EmbeddingConfigError, load_config

log = logging.getLogger(__name__)


class LocalE5Provider:
    def __init__(self, config: EmbeddingConfig, model_path: str):
        from sentence_transformers import SentenceTransformer  # optional dependency, imported lazily
        self.config = config
        self._model = SentenceTransformer(model_path, device="cpu", local_files_only=True)

    def _encode(self, prefix: str, text: str) -> tuple[float, ...]:
        vector = self._model.encode(prefix + text, normalize_embeddings=True)
        return tuple(float(x) for x in vector)

    def embed(self, text: str) -> tuple[float, ...]:
        """Query side (search)."""
        return self._encode("query: ", text)

    def embed_passage(self, text: str) -> tuple[float, ...]:
        """Document side (backfill)."""
        return self._encode("passage: ", text)


@lru_cache(maxsize=1)
def get_embedder() -> LocalE5Provider | None:
    """Process-wide embedder, or None (semantic search off) when unconfigured or unusable."""
    try:
        config = load_config(os.environ)
        if config is None or config.provider != "local_e5":
            return None
        path = os.environ.get("SEMANTIC_E5_MODEL_PATH", "")
        if not path or not os.path.isdir(path):
            raise EmbeddingConfigError("SEMANTIC_E5_MODEL_PATH is not a directory")
        return LocalE5Provider(config, path)
    except Exception as exc:  # optional capability: log the class only, keep serving keyword search
        log.warning("semantic search disabled: %s", type(exc).__name__)
        return None
