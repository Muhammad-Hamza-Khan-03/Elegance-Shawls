"""Gemini adapter: maps one explicit batchEmbedContents request/response. No fallback, no other endpoint."""
import httpx

from ..config import EvalConfig
from ..provider import (
    ConfigError,
    EmbeddingLimits,
    EmbeddingResult,
    MalformedResponseError,
    ProviderRequestError,
)
from ..validation import validate_inputs, validate_vectors

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class GeminiEmbeddingProvider:
    provider = "gemini"

    def __init__(self, config: EvalConfig, dimension: int, limits: EmbeddingLimits | None = None,
                 transport: httpx.BaseTransport | None = None):
        if config.provider != self.provider:
            raise ConfigError("config is not for gemini")
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension < 1:
            raise ConfigError("dimension must be a positive integer")
        self.model, self.dimension = config.model, dimension
        self.limits = limits or EmbeddingLimits()
        self._key = config.api_key
        self._transport = transport  # tests inject httpx.MockTransport; None means the real network

    def _body(self, texts) -> dict:
        model = f"models/{self.model}"
        return {"model": model, "requests": [
            {"model": model, "content": {"parts": [{"text": t}]}, "outputDimensionality": self.dimension}
            for t in texts
        ]}

    def _post(self, body: dict) -> tuple[httpx.Response, int]:
        url = f"{BASE_URL}/models/{self.model}:batchEmbedContents"
        headers = {"x-goog-api-key": self._key, "content-type": "application/json"}
        attempts = 0
        with httpx.Client(transport=self._transport, timeout=self.limits.timeout_s) as client:
            while True:
                attempts += 1
                try:
                    resp = client.post(url, headers=headers, json=body)
                    if resp.is_success:
                        return resp, attempts
                    failure = ProviderRequestError("provider returned an error status", status=resp.status_code)
                    retryable = resp.status_code in _RETRYABLE_STATUS
                except httpx.TransportError:
                    failure, retryable = ProviderRequestError("provider transport failure"), True
                if not retryable or attempts > self.limits.max_retries:
                    raise failure from None

    def embed(self, texts) -> EmbeddingResult:
        validate_inputs(texts, self.limits)
        resp, attempts = self._post(self._body(texts))
        try:
            data = resp.json()
            vectors = [item["values"] for item in data["embeddings"]]
        except (ValueError, KeyError, TypeError):
            raise MalformedResponseError("response is not a valid embeddings payload") from None
        vectors = validate_vectors(vectors, len(texts), self.dimension)
        raw_usage = data.get("usageMetadata")
        usage = ({k: v for k, v in raw_usage.items() if isinstance(v, int) and not isinstance(v, bool)}
                 if isinstance(raw_usage, dict) else {})
        return EmbeddingResult(
            vectors=vectors, provider=self.provider, model=self.model, dimension=self.dimension,
            item_count=len(vectors), usage=usage,
            request={"request_id": resp.headers.get("x-request-id"), "attempts": attempts},
        )
