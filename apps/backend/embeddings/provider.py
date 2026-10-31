"""Live-eval embedding provider contract: explicit provider/model in, vectors plus metadata out. No persistence, no fallback.

Separate from search/providers.py and the chat/LLM gateway. Error messages are fixed strings: they never carry input
text, credentials, headers, response bodies or vectors.
"""
from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence, runtime_checkable

MAX_BATCH = 16
MAX_CHARS = 8000
MAX_TIMEOUT_S = 60.0


class EmbeddingEvalError(Exception):
    """Typed, redacted failure. `code` is a stable machine-readable slug; str(exc) is a fixed message."""

    code = "embedding_eval_error"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.code)


class ConfigError(EmbeddingEvalError):
    code = "config_error"


class UnsupportedProviderError(EmbeddingEvalError):
    code = "unsupported_provider"


class InputError(EmbeddingEvalError):
    code = "invalid_input"


class ProviderRequestError(EmbeddingEvalError):
    code = "provider_request_failed"

    def __init__(self, message: str | None = None, *, status: int | None = None):
        super().__init__(message)
        self.status = status


class MalformedResponseError(EmbeddingEvalError):
    code = "malformed_response"


@dataclass(frozen=True)
class EmbeddingLimits:
    max_batch: int = MAX_BATCH
    max_chars: int = MAX_CHARS
    timeout_s: float = 30.0
    max_retries: int = 1  # transport-level only; the adapter is the single place retries happen

    def __post_init__(self):
        if not 1 <= self.max_batch <= MAX_BATCH:
            raise ConfigError(f"max_batch must be 1-{MAX_BATCH}")
        if not 1 <= self.max_chars <= MAX_CHARS:
            raise ConfigError(f"max_chars must be 1-{MAX_CHARS}")
        if not 0 < self.timeout_s <= MAX_TIMEOUT_S:
            raise ConfigError(f"timeout_s must be in (0, {MAX_TIMEOUT_S}]")
        if self.max_retries not in (0, 1):
            raise ConfigError("max_retries must be 0 or 1")


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    provider: str
    model: str
    dimension: int
    item_count: int
    usage: Mapping[str, int] = field(default_factory=dict)
    request: Mapping[str, object] = field(default_factory=dict)  # e.g. request_id, attempts


@runtime_checkable
class EmbeddingProvider(Protocol):
    provider: str
    model: str
    dimension: int
    limits: EmbeddingLimits

    def embed(self, texts: Sequence[str]) -> EmbeddingResult: ...
