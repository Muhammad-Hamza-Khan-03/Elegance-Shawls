"""Local multilingual-e5-base adapter: CPU-only, offline, one pinned model. No download, no network, no fallback.

sentence-transformers is an optional dependency (requirements-local-e5.txt), imported lazily. A missing package or
missing/unpinned/mismatched local model is a typed refusal, never a silent download. Errors are fixed strings: no paths,
texts or vectors.

Provenance: the model must be a local directory plus its expected revision, the tree digest printed by
`python -m embeddings.providers.local_e5 <model dir>` (sha256 over every file's relative path and content). The digest is
recomputed at load and must match, so a swapped or partial weights directory fails closed.

Timeout: encode() cannot be interrupted safely (torch, shared interpreter), so it runs in a daemon thread that is
abandoned on timeout and the provider then refuses every later call. That bounds the caller, not the CPU the stuck
thread burns; it is fail-closed, not a hard kill.
"""
import contextlib
import hashlib
import os
import re
import socket
import sys
import threading
from pathlib import Path

from ..config import EvalConfig
from ..provider import ConfigError, EmbeddingLimits, EmbeddingResult, ProviderRequestError
from ..validation import validate_inputs, validate_vectors

MODEL = "intfloat/multilingual-e5-base"
DIMENSION = 768
PREFIXES = {"query": "query: ", "passage": "passage: "}
TIMEOUT_ENFORCEMENT = "thread_abandoned_fail_closed_no_hard_kill"


class MissingLocalModelError(ConfigError):
    code = "missing_local_model"


class UnpinnedModelError(ConfigError):
    code = "unpinned_model"


class ModelRevisionMismatchError(ConfigError):
    code = "model_revision_mismatch"


class LocalDependencyError(ConfigError):
    code = "local_dependency_missing"


class NetworkBlockedError(ConfigError):
    code = "network_blocked"


@contextlib.contextmanager
def _no_network():
    """Any outbound connect or DNS lookup raises, so an accidental download cannot happen. Yields a `tripped` list."""
    tripped: list[bool] = []

    def blocked(*_, **__):
        tripped.append(True)
        raise OSError("network access is blocked for the local provider")
    saved = (socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo)
    socket.socket.connect = socket.socket.connect_ex = blocked
    socket.getaddrinfo = blocked
    try:
        yield tripped
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = saved


def model_tree_digest(path: str | Path) -> str:
    """sha256 over sorted (relative path, file sha256) pairs; symlinks (HF snapshots) are followed. Raises if no files."""
    root, lines = Path(path), []
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        h = hashlib.sha256()
        with f.open("rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        lines.append(f"{f.relative_to(root).as_posix()}\0{h.hexdigest()}\n")
    if not lines:
        raise MissingLocalModelError("local model directory holds no files")
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def _load_model(ref: str, cache_dir: str | None):
    os.environ["HF_HUB_OFFLINE"] = os.environ["TRANSFORMERS_OFFLINE"] = "1"  # before the library is imported
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise LocalDependencyError("sentence-transformers is not installed: pip install -r requirements-local-e5.txt") from None
    return SentenceTransformer(ref, device="cpu", cache_folder=cache_dir, local_files_only=True)


class LocalE5EmbeddingProvider:
    provider = "local_e5"

    def __init__(self, config: EvalConfig, dimension: int = DIMENSION, limits: EmbeddingLimits | None = None,
                 options: dict | None = None):
        """`options` takes the build_provider `transport` slot (no HTTP here): model_path and revision are both required."""
        opts = options or {}
        model_path, revision, cache_dir = opts.get("model_path"), opts.get("revision"), opts.get("cache_dir")
        if config.provider != self.provider:
            raise ConfigError("config is not for local_e5")
        if config.model != MODEL:
            raise ConfigError(f"local_e5 is pinned to {MODEL}")
        if isinstance(dimension, bool) or dimension != DIMENSION:
            raise ConfigError(f"local_e5 dimension must be {DIMENSION}")
        self.model, self.dimension = MODEL, DIMENSION
        self.limits = limits or EmbeddingLimits()
        if not model_path or not Path(model_path).is_dir():
            raise MissingLocalModelError("a local model directory is required (--local-model-path)")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
            raise UnpinnedModelError("a 64-hex model revision is required (--local-model-revision)")
        if model_tree_digest(model_path) != revision:
            raise ModelRevisionMismatchError("local model files do not match the pinned revision")
        self.revision, self._stuck = revision, False
        with _no_network() as tripped:
            try:
                self._model = _load_model(model_path, cache_dir)
            except ConfigError:
                raise
            except Exception:
                if tripped:
                    raise NetworkBlockedError("the local model needed network access; provide it offline") from None
                raise MissingLocalModelError("local model could not be loaded offline") from None

    def _encode(self, prefixed: list[str]):
        if self._stuck:
            raise ProviderRequestError("local provider is disabled after a timeout")
        box: dict = {}

        def work():
            try:
                box["out"] = self._model.encode(prefixed, batch_size=len(prefixed), normalize_embeddings=True,
                                                convert_to_numpy=True, show_progress_bar=False)
            except BaseException:
                box["failed"] = True

        worker = threading.Thread(target=work, daemon=True)
        with _no_network() as tripped:
            worker.start()
            worker.join(self.limits.timeout_s)
        if worker.is_alive():
            self._stuck = True  # the thread cannot be killed; refuse all further work instead
            raise ProviderRequestError("local inference exceeded the timeout; provider disabled")
        if box.get("failed") or "out" not in box:
            raise ProviderRequestError("local network access blocked" if tripped else "local inference failed")
        out = box["out"]
        return out.tolist() if hasattr(out, "tolist") else out

    def embed(self, texts, *, kind: str = "passage") -> EmbeddingResult:
        if kind not in PREFIXES:
            raise ConfigError("kind must be query or passage")
        validate_inputs(texts, self.limits)
        vectors = validate_vectors(self._encode([PREFIXES[kind] + t for t in texts]), len(texts), self.dimension)
        return EmbeddingResult(vectors=vectors, provider=self.provider, model=self.model, dimension=self.dimension,
                               item_count=len(vectors),
                               request={"attempts": 1, "kind": kind, "device": "cpu", "model_revision": self.revision})


if __name__ == "__main__":  # print the revision to pin for a model directory you downloaded yourself
    print(model_tree_digest(sys.argv[1]))
