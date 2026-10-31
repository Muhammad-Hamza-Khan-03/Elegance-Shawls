import sys
import types

import pytest

from semantic import local_e5
from semantic.embeddings import EmbeddingConfig

ENV = {"SEMANTIC_EMBEDDING_PROVIDER": "local_e5", "SEMANTIC_EMBEDDING_MODEL": "intfloat/multilingual-e5-base",
       "SEMANTIC_EMBEDDING_DIMENSIONS": "768"}


@pytest.fixture(autouse=True)
def fresh():
    local_e5.get_embedder.cache_clear()
    yield
    local_e5.get_embedder.cache_clear()


def test_unconfigured_or_unusable_means_semantic_search_off(monkeypatch, tmp_path):
    for key in (*ENV, "SEMANTIC_E5_MODEL_PATH"):
        monkeypatch.delenv(key, raising=False)
    assert local_e5.get_embedder() is None
    local_e5.get_embedder.cache_clear()
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    assert local_e5.get_embedder() is None                      # no model path
    monkeypatch.setenv("SEMANTIC_E5_MODEL_PATH", str(tmp_path))
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    local_e5.get_embedder.cache_clear()
    assert local_e5.get_embedder() is None                      # dependency missing: degrade, never raise


def test_query_and_passage_prefixes_and_offline_load(monkeypatch, tmp_path):
    seen = {}

    class Stub:
        def __init__(self, path, **kw):
            seen["load"] = (path, kw)

        def encode(self, text, **kw):
            seen["text"] = text
            return [0.5] * 768

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=Stub))
    provider = local_e5.LocalE5Provider(EmbeddingConfig("local_e5", "intfloat/multilingual-e5-base", 768), str(tmp_path))
    assert seen["load"][1] == {"device": "cpu", "local_files_only": True}
    provider.embed("garam chaadar")
    assert seen["text"] == "query: garam chaadar"
    assert len(provider.embed_passage("Wool Shawl")) == 768 and seen["text"] == "passage: Wool Shawl"
