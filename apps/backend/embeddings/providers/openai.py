"""OpenAI adapter (last-resort comparison only): one explicit /v1/embeddings mapping for one allowlisted model.

Pinned to text-embedding-3-small at 768 dimensions. No model discovery, no fallback, no other endpoint. The key travels
only in the Authorization header; errors are fixed strings with no input, key, response body or vectors.
"""
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

URL = "https://api.openai.com/v1/embeddings"
MODEL = "text-embedding-3-small"
DIMENSION = 768
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class OpenAIEmbeddingProvider:
    provider = "openai"

    def __init__(self, config: EvalConfig, dimension: int, limits: EmbeddingLimits | None = None,
                 transport: httpx.BaseTransport | None = None):
        if config.provider != self.provider:
            raise ConfigError("config is not for openai")
        if config.model != MODEL:
            raise ConfigError(f"openai model must be exactly {MODEL}")
        if isinstance(dimension, bool) or dimension != DIMENSION:
            raise ConfigError(f"openai dimension must be exactly {DIMENSION}")
        self.model, self.dimension = config.model, dimension
        self.limits = limits or EmbeddingLimits()
        self._key = config.api_key
        self._transport = transport  # tests inject httpx.MockTransport; None means the real network

    def _post(self, texts) -> tuple[httpx.Response, int]:
        body = {"model": self.model, "input": list(texts), "dimensions": self.dimension, "encoding_format": "float"}
        headers = {"authorization": f"Bearer {self._key}", "content-type": "application/json"}
        attempts = 0
        with httpx.Client(transport=self._transport, timeout=self.limits.timeout_s, follow_redirects=False) as client:
            while True:
                attempts += 1
                try:
                    resp = client.post(URL, headers=headers, json=body)
                    if resp.is_success:
                        return resp, attempts
                    status = resp.status_code
                    msg = ("provider rejected the credentials" if status in (401, 403)
                           else "provider rate limited the request" if status == 429
                           else "provider returned an error status")
                    failure, retryable = ProviderRequestError(msg, status=status), status in _RETRYABLE_STATUS
                except httpx.TransportError:
                    failure, retryable = ProviderRequestError("provider transport failure"), True
                if not retryable or attempts > self.limits.max_retries:
                    raise failure from None

    def embed(self, texts) -> EmbeddingResult:
        validate_inputs(texts, self.limits)
        resp, attempts = self._post(texts)
        try:
            data = resp.json()
            items = data["data"]
            if data["model"] != self.model or not isinstance(items, list):  # a silent model substitution is a failure
                raise ValueError
            for i in items:  # exact int (bool/float rejected) and the documented object tag
                if not isinstance(i, dict) or i["object"] != "embedding" or type(i["index"]) is not int:
                    raise ValueError
            if sorted(i["index"] for i in items) != list(range(len(texts))):
                raise ValueError
            vectors = [i["embedding"] for i in sorted(items, key=lambda i: i["index"])]
        except (ValueError, KeyError, TypeError):
            raise MalformedResponseError("response is not a valid embeddings payload") from None
        vectors = validate_vectors(vectors, len(texts), self.dimension)
        raw_usage = data.get("usage")
        usage = ({k: v for k, v in raw_usage.items() if isinstance(v, int) and not isinstance(v, bool)}
                 if isinstance(raw_usage, dict) else {})
        return EmbeddingResult(
            vectors=vectors, provider=self.provider, model=self.model, dimension=self.dimension,
            item_count=len(vectors), usage=usage,
            request={"request_id": resp.headers.get("x-request-id"), "attempts": attempts},
        )
