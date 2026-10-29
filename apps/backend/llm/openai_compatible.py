"""Built-in OpenAI-compatible chat client for Groq, Gemini, OpenRouter and Ollama.

Used instead of LiteLLM for these providers because LiteLLM's `filelock<4` pin conflicts with the
audited dependency set (see requirements-llm.txt). Keys are read from provider environment
variables only, travel only in the Authorization header, and are never logged or put in errors.
Errors carry the HTTP status, never the response body (providers can echo prompts).
"""
import os

import httpx

from configuration.config import settings
from llm.fake import ProviderReply

# provider -> (base URL, API key variable; None = no key, e.g. a local Ollama)
PROVIDERS: dict[str, tuple[str, str | None]] = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
}


class ProviderError(RuntimeError):
    pass


def supports(model: str) -> bool:
    return model.split("/", 1)[0].lower() in PROVIDERS


def _base_url(provider: str) -> str:
    # OLLAMA_BASE_URL / <PROVIDER>_BASE_URL let operators point at a self-hosted gateway.
    return os.environ.get(f"{provider.upper()}_BASE_URL", PROVIDERS[provider][0]).rstrip("/")


def _cost(usage: dict, input_tokens: int, output_tokens: int) -> float:
    if isinstance(usage.get("cost"), (int, float)):  # OpenRouter reports the charged cost
        return float(usage["cost"])
    # shortcut: one global price pair, not per model; zero (the free-tier default) means "unpriced".
    return (input_tokens * settings.llm_price_per_million_input_usd
            + output_tokens * settings.llm_price_per_million_output_usd) / 1_000_000


async def openai_compatible_completion(model: str, messages: list[dict], timeout: float,
                                       transport: httpx.AsyncBaseTransport | None = None) -> ProviderReply:
    provider, _, upstream_model = model.partition("/")
    provider = provider.lower()
    base, key_env = PROVIDERS[provider]
    headers = {"content-type": "application/json"}
    if key_env:
        key = os.environ.get(key_env)
        if not key:
            raise ProviderError(f"{key_env} is not set")  # names the variable, never a value
        headers["authorization"] = f"Bearer {key}"
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        response = await client.post(f"{_base_url(provider)}/chat/completions", headers=headers,
                                     json={"model": upstream_model, "messages": messages, "stream": False})
    if response.status_code >= 400:
        raise ProviderError(f"{provider} returned HTTP {response.status_code}")
    data = response.json()
    usage = data.get("usage") or {}
    input_tokens, output_tokens = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    return ProviderReply(
        text=(data["choices"][0]["message"].get("content") or ""),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_cost(usage, input_tokens, output_tokens),
    )
