"""Local-only semantic flag: default off, environment refusal, typed failures, adapter contract. No model, no network."""
import asyncio
from types import SimpleNamespace

import pytest

from configuration.config import settings
from embeddings.provider import EmbeddingLimits as EvalLimits, ProviderRequestError
from embeddings.providers.local_e5 import DIMENSION, MODEL
from search import hybrid, local_e5
from search.providers import EmbeddingError, FakeEmbeddingProvider, NonRetryableEmbeddingError, embed_checked

REVISION = "a" * 64


class Inner:
    revision, limits = REVISION, EvalLimits()

    def __init__(self, boom=False):
        self.calls, self.boom = [], boom

    def embed(self, texts, *, kind):
        self.calls.append((list(texts), kind))
        if self.boom:
            raise ProviderRequestError("local inference failed")
        return SimpleNamespace(vectors=[[0.5] * DIMENSION for _ in texts])


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(local_e5, "_loaded", {})
    for key, value in (("local_semantic_search_enabled", True), ("environment", "development"), ("embedding_enabled", True),
                       ("embedding_provider", "local_e5"), ("embedding_dimensions", DIMENSION),
                       ("local_e5_model_path", "/models/e5"), ("local_e5_model_revision", REVISION)):
        monkeypatch.setattr(settings, key, value)


def run(coro):
    return asyncio.run(coro)


def test_flag_defaults_off():
    fields = type(settings).model_fields
    assert fields["local_semantic_search_enabled"].default is False and fields["local_e5_model_path"].default == ""


# "staging" is deliberately allowed since staging/e5-semantic-activation (isolated E5 rehearsal with the pinned offline model); it is no longer refused.
@pytest.mark.parametrize("env", ["production", "prod", "", "preview", "Production "])
def test_refused_outside_local_environments(monkeypatch, env):
    monkeypatch.setattr(settings, "environment", env)
    monkeypatch.setattr(local_e5, "LocalE5EmbeddingProvider", lambda *a: pytest.fail("model must not load"))
    with pytest.raises(NonRetryableEmbeddingError):
        local_e5.local_provider()
    assert run(hybrid.query_vector("cozy stole", enabled=True, name="local_e5", dimensions=DIMENSION)) == (None, None)


def test_refused_when_flag_off_or_model_missing(monkeypatch):
    monkeypatch.setattr(settings, "local_semantic_search_enabled", False)
    with pytest.raises(NonRetryableEmbeddingError):
        local_e5.local_provider()
    monkeypatch.setattr(settings, "local_semantic_search_enabled", True)
    monkeypatch.setattr(settings, "local_e5_model_path", "/nonexistent/model")     # real provider: typed refusal, no download
    with pytest.raises(NonRetryableEmbeddingError):
        local_e5.local_provider()
    assert run(hybrid.query_vector("cozy stole", enabled=True, name="local_e5", dimensions=DIMENSION)) == (None, None)


def test_flag_off_leaves_other_provider_names_failing_closed(monkeypatch):
    monkeypatch.setattr(settings, "local_semantic_search_enabled", False)
    for name in ("openai", "gemini", ""):
        assert run(hybrid.query_vector("cozy stole", enabled=True, name=name, dimensions=DIMENSION)) == (None, None)


def test_query_path_uses_the_query_prefix_and_identity(monkeypatch):
    inner = Inner()
    monkeypatch.setattr(local_e5, "LocalE5EmbeddingProvider", lambda *a: inner)
    provider, vector = run(hybrid.query_vector("cozy stole", enabled=True, name="local_e5", dimensions=DIMENSION))
    assert (provider.name, provider.model, provider.model_revision) == ("local_e5", MODEL, REVISION)
    assert len(vector) == DIMENSION and inner.calls == [(["cozy stole"], "query")]
    assert local_e5.local_provider("passage")._kind == "passage" and len(local_e5._loaded) == 1   # one load, per-kind adapter


def test_provider_failure_and_wrong_dimensions_fall_back_to_lexical(monkeypatch):
    monkeypatch.setattr(local_e5, "LocalE5EmbeddingProvider", lambda *a: Inner(boom=True))
    assert run(hybrid.query_vector("cozy stole", enabled=True, name="local_e5", dimensions=DIMENSION)) == (None, None)
    with pytest.raises(EmbeddingError):
        run(embed_checked(local_e5.local_provider(), ["x"]))
    monkeypatch.setattr(local_e5, "LocalE5EmbeddingProvider", lambda *a: Inner())
    assert run(hybrid.query_vector("cozy stole", enabled=True, name="local_e5", dimensions=32)) == (None, None)


def test_search_version_pins_model_revision_but_leaves_fake_cursors_unchanged(monkeypatch):
    monkeypatch.setattr(local_e5, "LocalE5EmbeddingProvider", lambda *a: Inner())
    local = hybrid.search_version(local_e5.local_provider(), "idx")
    assert REVISION in local and local != hybrid.search_version(None, "idx")
    assert hybrid.search_version(FakeEmbeddingProvider(), "idx") == f"{hybrid.SEARCH_VERSION}|fake/fake-sha256-v1/idx"
    assert hybrid.RRF_K == 60
