"""Local-only EmbeddingGemma 2 (text) bridge for /v1/search/hybrid. Never for production; same gates as local_e5.

Needs LOCAL_SEMANTIC_SEARCH_ENABLED, a local ENVIRONMENT, and a model dir whose Hugging Face download metadata all name
the pinned 40-hex commit. Loads offline (local_files_only, no network). Any refusal/load/inference error is a typed
EmbeddingError, which the search path turns into lexical-only results (semantic=false).
The HF revision metadata is checked, then the canonical tree digest (.cache excluded; relative path + NUL + raw file sha256)
and model.safetensors sha256 are verified on every first load. Inference has no abandonable thread; embed_checked's timeout bounds the caller only.
"""
import hashlib
import re
from pathlib import Path
from types import SimpleNamespace

from configuration.config import settings
from embeddings.provider import ConfigError, EmbeddingLimits, EmbeddingEvalError, ProviderRequestError
from embeddings.providers.local_e5 import _load_model, _no_network
from search.local_e5 import LOCAL_ENVIRONMENTS, LocalE5Adapter
from search.providers import EmbeddingProvider, NonRetryableEmbeddingError

MODEL = "google/embeddinggemma-2"
MODEL_REVISION = "f9972ac22e696a105c482202646979e33e4b5a1e"
DIMENSION = 768
PROMPTS = {"query": "query", "passage": "document"}   # prompt names defined in the model's config_sentence_transformers.json
TREE_SHA = "8338594ef62c913285891b775b6c3084e518001f499c1f97df61904c57ad708b"
FILE_SHA = "197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79"   # model.safetensors
_loaded: dict[tuple[str, str], "LocalGemmaProvider"] = {}


def _verify_revision(path: str, revision: str) -> None:
    if revision != MODEL_REVISION or not re.fullmatch(r"[0-9a-f]{40}", revision or ""):
        raise ConfigError("the approved EmbeddingGemma 2 revision is required")
    meta = list((Path(path) / ".cache/huggingface/download").glob("*.metadata")) if Path(path).is_dir() else []
    if not meta or any(m.read_text().split("\n", 1)[0].strip() != revision for m in meta):
        raise ConfigError("local model files do not match the pinned revision")


def _file_sha(f: Path) -> bytes:
    h = hashlib.sha256()
    with f.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.digest()


def _verify_digests(path: str) -> None:
    base, tree, weights = Path(path), hashlib.sha256(), None
    try:
        for f in sorted(base.rglob("*")):
            rel = f.relative_to(base)
            if f.is_file() and ".cache" not in rel.parts:
                d = _file_sha(f)
                tree.update(rel.as_posix().encode() + b"\0" + d)
                if rel.as_posix() == "model.safetensors":
                    weights = d.hex()
    except OSError:
        raise ConfigError("local model files could not be read") from None
    if tree.hexdigest() != TREE_SHA or weights != FILE_SHA:
        raise ConfigError("local model files do not match the approved digest")


class LocalGemmaProvider:
    def __init__(self, path: str, revision: str):
        _verify_revision(path, revision)
        _verify_digests(path)
        self.revision, self.limits = revision, EmbeddingLimits()
        with _no_network():
            try:
                self._model = _load_model(path, None)
            except ConfigError:
                raise
            except Exception:
                raise ConfigError("local model could not be loaded offline") from None

    def embed(self, texts, *, kind: str):
        try:
            out = self._model.encode(list(texts), prompt_name=PROMPTS[kind], normalize_embeddings=True,
                                     convert_to_numpy=True, show_progress_bar=False)
            return SimpleNamespace(vectors=out.tolist() if hasattr(out, "tolist") else out)
        except Exception:
            raise ProviderRequestError("local inference failed") from None


class LocalGemmaAdapter(LocalE5Adapter):
    name, model, dimensions = "local_embeddinggemma2", MODEL, DIMENSION


def local_provider(kind: str = "query") -> EmbeddingProvider:
    if not settings.local_semantic_search_enabled:
        raise NonRetryableEmbeddingError("local semantic search is disabled")
    if settings.environment.strip().lower() not in LOCAL_ENVIRONMENTS:
        raise NonRetryableEmbeddingError("local semantic search is refused outside a local environment")
    key = (settings.local_gemma_model_path, settings.local_gemma_model_revision)
    try:
        inner = _loaded.get(key) or _loaded.setdefault(key, LocalGemmaProvider(*key))
    except Exception:  # any load failure (not BaseException) must degrade to lexical search
        raise NonRetryableEmbeddingError("local embeddinggemma model is unavailable") from None
    return LocalGemmaAdapter(inner, kind)
