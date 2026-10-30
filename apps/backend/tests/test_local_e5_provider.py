"""Local e5 provider: prefixes, 768-d validation, offline guard, provenance, timeout, typed refusals.
The model loader is mocked: no download, no real weights."""
import math
import os
import re
import socket
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from embeddings.config import EvalConfig
from embeddings.provider import (ConfigError, EmbeddingLimits, InputError, MalformedResponseError, ProviderRequestError)
from embeddings.providers import build_provider, local_e5
from embeddings.providers.local_e5 import (MODEL, LocalDependencyError, LocalE5EmbeddingProvider, MissingLocalModelError,
                                           ModelRevisionMismatchError, NetworkBlockedError, UnpinnedModelError,
                                           model_tree_digest)

CFG = EvalConfig("local_e5", MODEL, "")
BACKEND = Path(__file__).resolve().parents[1]


class FakeModel:
    def __init__(self, out=None, boom=None):
        self.calls, self.out, self.boom = [], out, boom

    def encode(self, texts, **kw):
        self.calls.append((list(texts), kw))
        if self.boom:
            raise self.boom
        return self.out if self.out is not None else [[0.5] * 768 for _ in texts]


@pytest.fixture
def mdir(tmp_path):
    """A stand-in 'downloaded' model directory: the provider only hashes it and hands it to the (mocked) loader."""
    d = tmp_path / "e5"
    (d / "sub").mkdir(parents=True)
    (d / "config.json").write_text("{}")
    (d / "sub" / "weights.bin").write_bytes(b"\x00\x01fake-weights")
    return d


def opts(d, **extra):
    return {"model_path": str(d), "revision": model_tree_digest(d), **extra}


@pytest.fixture
def model(monkeypatch):
    m = FakeModel()
    monkeypatch.setattr(local_e5, "_load_model", lambda ref, cache: m)
    return m


def test_prefixes_dimension_and_exact_metadata(model, mdir):
    p = LocalE5EmbeddingProvider(CFG, 768, options=opts(mdir))
    q = p.embed(["red shawl"], kind="query")
    d = p.embed(["red shawl", "blue stole"])
    assert [c[0] for c in model.calls] == [["query: red shawl"], ["passage: red shawl", "passage: blue stole"]]
    assert all(c[1]["normalize_embeddings"] and not c[1]["show_progress_bar"] for c in model.calls)
    assert (q.provider, q.model, q.dimension, q.item_count) == ("local_e5", "intfloat/multilingual-e5-base", 768, 1)
    assert d.item_count == 2 and len(d.vectors[0]) == 768
    assert q.request == {"attempts": 1, "kind": "query", "device": "cpu", "model_revision": model_tree_digest(mdir)}


def test_registered_and_pinned(model, mdir):
    assert isinstance(build_provider(CFG, 768, None, opts(mdir)), LocalE5EmbeddingProvider)
    for cfg, dim in ((EvalConfig("local_e5", "intfloat/multilingual-e5-small", ""), 768), (CFG, 384), (CFG, True),
                     (EvalConfig("gemini", MODEL, "k"), 768)):
        with pytest.raises(ConfigError):
            LocalE5EmbeddingProvider(cfg, dim, options=opts(mdir))


@pytest.mark.parametrize("out", [[[0.5] * 768],                              # count
                                 [[0.5] * 767, [0.5] * 767],                 # dimension
                                 [[math.nan] * 768, [0.5] * 768],
                                 [[math.inf] * 768, [0.5] * 768]])
def test_strict_output_validation(monkeypatch, mdir, out):
    monkeypatch.setattr(local_e5, "_load_model", lambda ref, cache: FakeModel(out))
    with pytest.raises(MalformedResponseError):
        LocalE5EmbeddingProvider(CFG, 768, options=opts(mdir)).embed(["a", "b"])


def test_input_limits_and_bad_kind(model, mdir):
    p = LocalE5EmbeddingProvider(CFG, 768, EmbeddingLimits(max_batch=2, max_chars=5), opts(mdir))
    for bad in ([], ["a", "b", "c"], ["toolong"], [" "], "abc"):
        with pytest.raises(InputError):
            p.embed(bad)
    with pytest.raises(ConfigError):
        p.embed(["a"], kind="document")
    assert model.calls == []


# --- provenance: no path, no revision, or a different tree means no provider (fail closed, nothing loaded) ----------

def test_unpinned_or_missing_model_fails_closed_without_loading(monkeypatch, mdir, tmp_path):
    loads = []
    monkeypatch.setattr(local_e5, "_load_model", lambda ref, cache: loads.append(ref) or FakeModel())
    good = opts(mdir)
    cases = [({}, MissingLocalModelError, "missing_local_model"),                                  # no discovery by name
             ({"model_path": str(tmp_path / "nope"), "revision": good["revision"]}, MissingLocalModelError, "missing_local_model"),
             ({"model_path": str(mdir)}, UnpinnedModelError, "unpinned_model"),
             ({"model_path": str(mdir), "revision": "main"}, UnpinnedModelError, "unpinned_model"),
             ({"model_path": str(mdir), "revision": "A" * 64}, UnpinnedModelError, "unpinned_model"),
             ({"model_path": str(mdir), "revision": "0" * 64}, ModelRevisionMismatchError, "model_revision_mismatch")]
    for o, exc, code in cases:
        with pytest.raises(exc) as e:
            LocalE5EmbeddingProvider(CFG, 768, options=o)
        assert e.value.code == code and str(mdir) not in str(e.value)
    with pytest.raises(MissingLocalModelError):
        LocalE5EmbeddingProvider(CFG, 768)
    (mdir / "sub" / "weights.bin").write_bytes(b"tampered")
    with pytest.raises(ModelRevisionMismatchError):
        LocalE5EmbeddingProvider(CFG, 768, options=good)
    assert loads == []


def test_tree_digest_is_deterministic_and_content_and_name_sensitive(mdir, tmp_path):
    first = model_tree_digest(mdir)
    assert re.fullmatch(r"[0-9a-f]{64}", first) and model_tree_digest(mdir) == first
    (mdir / "config.json").write_text("{ }")
    assert model_tree_digest(mdir) != first
    (mdir / "config.json").write_text("{}")
    (mdir / "config.json").rename(mdir / "other.json")
    assert model_tree_digest(mdir) != first
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(MissingLocalModelError):
        model_tree_digest(empty)


# --- cached-model path: the real loader with a fake sentence_transformers module -------------------------------------

def test_cached_model_loads_offline_cpu_local_files_only(monkeypatch, mdir):
    seen = {}

    class FakeST(FakeModel):
        def __init__(self, ref, **kw):
            super().__init__()
            seen.update(ref=ref, **kw, hf=os.environ.get("HF_HUB_OFFLINE"), tf=os.environ.get("TRANSFORMERS_OFFLINE"))
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=FakeST))
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")  # registers teardown restore; the loader must overwrite it
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "0")
    r = LocalE5EmbeddingProvider(CFG, 768, options=opts(mdir, cache_dir="/cache")).embed(["a"], kind="query")
    assert seen == {"ref": str(mdir), "device": "cpu", "cache_folder": "/cache", "local_files_only": True, "hf": "1", "tf": "1"}
    assert r.item_count == 1 and r.dimension == 768


def test_loader_failure_is_typed_and_redacted(monkeypatch, mdir):
    def absent(ref, cache):
        raise OSError(f"secret path {ref} not found")
    monkeypatch.setattr(local_e5, "_load_model", absent)
    with pytest.raises(MissingLocalModelError) as e:
        LocalE5EmbeddingProvider(CFG, 768, options=opts(mdir))
    assert "secret" not in str(e.value) and str(mdir) not in str(e.value)


def test_missing_optional_dependency_names_the_requirements_file(monkeypatch, mdir):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)  # makes the import raise ImportError
    with pytest.raises(LocalDependencyError) as e:
        LocalE5EmbeddingProvider(CFG, 768, options=opts(mdir))
    assert e.value.code == "local_dependency_missing" and "requirements-local-e5.txt" in str(e.value)


# --- no network, no fallback, redaction ------------------------------------------------------------------------------

def test_network_attempts_are_blocked_and_typed(monkeypatch, mdir):
    originals = (socket.socket.connect, socket.getaddrinfo)

    def load(ref, cache):
        socket.getaddrinfo("huggingface.co", 443)
        return FakeModel()
    monkeypatch.setattr(local_e5, "_load_model", load)
    with pytest.raises(NetworkBlockedError):
        LocalE5EmbeddingProvider(CFG, 768, options=opts(mdir))
    m = FakeModel()
    m.encode = lambda texts, **kw: socket.socket().connect(("203.0.113.1", 80))
    monkeypatch.setattr(local_e5, "_load_model", lambda ref, cache: m)
    with pytest.raises(ProviderRequestError) as e:
        LocalE5EmbeddingProvider(CFG, 768, options=opts(mdir)).embed(["a"])
    assert "blocked" in str(e.value)
    assert (socket.socket.connect, socket.getaddrinfo) == originals  # guard is restored


def test_inference_errors_are_redacted_and_there_is_no_fallback(monkeypatch, mdir):
    monkeypatch.setattr(local_e5, "_load_model", lambda ref, cache: FakeModel(boom=RuntimeError("raw text: secret shawl")))
    with pytest.raises(ProviderRequestError) as e:
        LocalE5EmbeddingProvider(CFG, 768, options=opts(mdir)).embed(["secret shawl"])
    assert "secret" not in str(e.value) and e.value.__cause__ is None
    src = Path(local_e5.__file__).read_text(encoding="utf-8")
    assert not any(w in src for w in ("httpx", "requests", "urllib", "gemini", "openai", "groq", "from_pretrained"))


# --- timeout: a stuck encode() is abandoned (not killed) and the provider then refuses everything ----------------------

def test_stuck_encode_times_out_and_disables_the_provider(monkeypatch, mdir):
    release, started, calls = threading.Event(), threading.Event(), []
    m = FakeModel()

    def stuck(texts, **kw):
        calls.append(texts)
        started.set()
        release.wait(10)
        return [[0.5] * 768 for _ in texts]
    m.encode = stuck
    monkeypatch.setattr(local_e5, "_load_model", lambda ref, cache: m)
    p = LocalE5EmbeddingProvider(CFG, 768, EmbeddingLimits(timeout_s=0.05), opts(mdir))
    try:
        with pytest.raises(ProviderRequestError) as e:
            p.embed(["a"])
        assert started.is_set() and "timeout" in str(e.value)
        with pytest.raises(ProviderRequestError) as e:
            p.embed(["b"])
        assert "disabled" in str(e.value) and len(calls) == 1  # no second encode while the first is still stuck
    finally:
        release.set()
    assert "no_hard_kill" in local_e5.TIMEOUT_ENFORCEMENT  # the limitation is part of the reported contract


# --- packaging -------------------------------------------------------------------------------------------------------

def test_optional_requirement_is_exactly_pinned_and_not_in_core_requirements():
    reqs = (BACKEND / "requirements-local-e5.txt").read_text(encoding="utf-8").splitlines()
    pins = [line for line in reqs if line.startswith("sentence-transformers")]
    assert len(pins) == 1 and re.fullmatch(r"sentence-transformers==\d+\.\d+\.\d+", pins[0])
    for core in ("requirements.txt", "requirements-dev.txt", "requirements-llm.txt"):
        assert "sentence-transformers" not in (BACKEND / core).read_text(encoding="utf-8").lower().replace("_", "-")
