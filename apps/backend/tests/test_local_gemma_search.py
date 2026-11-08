"""EmbeddingGemma 2 local flag: off by default, pinned offline load + inference (skipped if the model/deps are absent),
failure-injection fallback to lexical, and the real /v1/search/hybrid route. No network, no database."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from configuration.config import settings
from database.pg import get_pg_session
from main import create_app
from search import hybrid, local_gemma
from search.providers import EmbeddingError, embed_checked

MODEL_DIR = "/home/hamza/.cache/elegance/embeddinggemma-2"
REVISION = "f9972ac22e696a105c482202646979e33e4b5a1e"
DIM = local_gemma.DIMENSION


class Inner:
    revision, limits = REVISION, local_gemma.LocalGemmaProvider.__init__.__globals__["EmbeddingLimits"]()

    def __init__(self, vec=None, boom=False):
        self.vec, self.boom = vec or [0.5] * DIM, boom

    def embed(self, texts, *, kind):
        if self.boom:
            raise local_gemma.ProviderRequestError("local inference failed")
        return type("R", (), {"vectors": [self.vec for _ in texts]})


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(local_gemma, "_loaded", {})
    for k, v in (("local_semantic_search_enabled", True), ("environment", "development"), ("embedding_enabled", True),
                 ("embedding_provider", "local_embeddinggemma2"), ("embedding_dimensions", DIM),
                 ("local_gemma_model_path", MODEL_DIR), ("local_gemma_model_revision", REVISION)):
        monkeypatch.setattr(settings, k, v)


def qv(**kw):
    kw = {"enabled": True, "name": "local_embeddinggemma2", "dimensions": DIM, **kw}
    return asyncio.run(hybrid.query_vector("cozy stole", **kw))


def test_flag_defaults_off():
    f = type(settings).model_fields
    assert f["local_semantic_search_enabled"].default is False and f["local_gemma_model_path"].default == ""


def test_flag_off_or_nonlocal_env_never_loads(monkeypatch):
    monkeypatch.setattr(local_gemma, "LocalGemmaProvider", lambda *a: pytest.fail("must not load"))
    monkeypatch.setattr(settings, "local_semantic_search_enabled", False)
    assert qv() == (None, None)
    monkeypatch.setattr(settings, "local_semantic_search_enabled", True)
    monkeypatch.setattr(settings, "environment", "production")
    assert qv() == (None, None)


def test_bad_revision_or_missing_dir_falls_back():
    for path, rev in ((MODEL_DIR, "0" * 40), ("/nonexistent", REVISION), (MODEL_DIR, "abc")):
        settings.local_gemma_model_path, settings.local_gemma_model_revision = path, rev
        assert qv() == (None, None)


def test_inference_and_dimension_failures_fall_back(monkeypatch):
    monkeypatch.setattr(local_gemma, "LocalGemmaProvider", lambda *a: Inner(boom=True))
    assert qv() == (None, None)
    monkeypatch.setattr(local_gemma, "_loaded", {})
    monkeypatch.setattr(local_gemma, "LocalGemmaProvider", lambda *a: Inner(vec=[0.1] * 5))   # wrong dimension from model
    assert qv() == (None, None)
    monkeypatch.setattr(local_gemma, "LocalGemmaProvider", lambda *a: Inner())
    assert qv(dimensions=32) == (None, None)
    with pytest.raises(EmbeddingError):
        asyncio.run(embed_checked(local_gemma.local_provider(), [" "]))


def test_identity_and_success_with_injected_model(monkeypatch):
    monkeypatch.setattr(local_gemma, "LocalGemmaProvider", lambda *a: Inner())
    provider, vec = qv()
    assert (provider.name, provider.model, provider.model_revision) == ("local_embeddinggemma2", local_gemma.MODEL, REVISION)
    assert len(vec) == DIM


def _client(monkeypatch):
    async def no_rows(*a, **k):
        return []
    monkeypatch.setattr("routes.search_routes.repo.search_batch", no_rows)
    app = create_app()
    app.dependency_overrides[get_pg_session] = lambda: None
    return TestClient(app)


def test_route_reports_semantic_true_then_false_on_failure(monkeypatch):
    c = _client(monkeypatch)
    monkeypatch.setattr(local_gemma, "LocalGemmaProvider", lambda *a: Inner())
    ok = c.post("/v1/search/hybrid", json={"q": "cozy stole"})
    assert ok.status_code == 200 and ok.json()["semantic"] is True
    monkeypatch.setattr(local_gemma, "_loaded", {})
    monkeypatch.setattr(local_gemma, "LocalGemmaProvider", lambda *a: Inner(boom=True))
    bad = c.post("/v1/search/hybrid", json={"q": "cozy stole"})
    assert bad.status_code == 200 and bad.json()["semantic"] is False


def test_route_generic_constructor_error_falls_back(monkeypatch):
    def boom(*a):
        raise RuntimeError("secret /path/leak")
    monkeypatch.setattr(local_gemma, "LocalGemmaProvider", boom)
    r = _client(monkeypatch).post("/v1/search/hybrid", json={"q": "cozy stole"})
    assert r.status_code == 200 and r.json()["semantic"] is False


def test_route_flag_off_is_lexical(monkeypatch):
    monkeypatch.setattr(settings, "local_semantic_search_enabled", False)
    r = _client(monkeypatch).post("/v1/search/hybrid", json={"q": "cozy stole"})
    assert r.status_code == 200 and r.json()["semantic"] is False


@pytest.mark.skipif(not Path(MODEL_DIR).is_dir() or importlib.util.find_spec("sentence_transformers") is None,
                    reason="pinned local model or sentence-transformers>=6.1 not installed")
def test_real_pinned_model_loads_offline_and_embeds():
    provider, vec = qv()
    assert provider is not None and len(vec) == DIM and abs(sum(x * x for x in vec) ** 0.5 - 1) <= 0.01  # bfloat16 on CPU gives ~0.9964


TREE_SHA = "8338594ef62c913285891b775b6c3084e518001f499c1f97df61904c57ad708b"
FILE_SHA = "197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79"


def test_prompt_names_exist_in_model_config():
    cfg = Path(MODEL_DIR) / "config_sentence_transformers.json"
    if not cfg.is_file():
        pytest.skip("pinned local model not present")
    assert set(local_gemma.PROMPTS.values()) <= set(json.loads(cfg.read_text())["prompts"])


@pytest.mark.skipif(not Path(MODEL_DIR).is_dir(), reason="pinned local model not present")
def test_pinned_model_tree_file_and_revision_digests():
    base = Path(MODEL_DIR)
    h = hashlib.sha256()   # canonical tree digest: relative path + NUL + raw file sha256, .cache excluded
    for f in sorted(base.rglob("*")):
        if f.is_file() and ".cache" not in f.relative_to(base).parts:
            h.update(f.relative_to(base).as_posix().encode() + b"\0" + hashlib.sha256(f.read_bytes()).digest())
    assert h.hexdigest() == TREE_SHA
    assert hashlib.sha256((base / "model.safetensors").read_bytes()).hexdigest() == FILE_SHA
    local_gemma._verify_revision(MODEL_DIR, REVISION)


def test_digest_mismatch_is_typed_and_falls_back(tmp_path, monkeypatch):
    meta = tmp_path / ".cache/huggingface/download"
    meta.mkdir(parents=True)
    (meta / "x.metadata").write_text(REVISION + "\n")
    (tmp_path / "model.safetensors").write_bytes(b"tampered")
    monkeypatch.setattr(local_gemma, "_load_model", lambda *a: pytest.fail("must not load unverified files"))
    with pytest.raises(local_gemma.ConfigError):
        local_gemma.LocalGemmaProvider(str(tmp_path), REVISION)
    settings.local_gemma_model_path = str(tmp_path)
    assert qv() == (None, None)


def test_startup_does_not_load_model(monkeypatch):
    monkeypatch.setattr(local_gemma, "LocalGemmaProvider", lambda *a: pytest.fail("must not load at startup"))
    create_app()
    assert local_gemma._loaded == {}
