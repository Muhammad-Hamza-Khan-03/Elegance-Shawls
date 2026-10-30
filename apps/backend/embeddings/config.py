"""Explicit eval allowlist and credentials. Reads only EMBEDDING_EVAL_* variables, never the chat/LLM settings."""
import os
import re
from dataclasses import dataclass, field
from typing import Mapping

from .provider import ConfigError

ALLOWLIST_VAR = "EMBEDDING_EVAL_ALLOWED_MODELS"
PROVIDERS = ("gemini", "groq")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _key_var(provider: str) -> str:
    return f"EMBEDDING_EVAL_{provider.upper()}_API_KEY"


@dataclass(frozen=True)
class EvalConfig:
    provider: str
    model: str
    api_key: str = field(repr=False)


def parse_allowlist(raw: str | None) -> frozenset[tuple[str, str]]:
    """`gemini/<model>,groq/<model>`. Empty, malformed, unknown-provider or duplicate entries reject the whole list."""
    if not raw or not raw.strip():
        raise ConfigError(f"{ALLOWLIST_VAR} is not set")
    entries: list[tuple[str, str]] = []
    for item in raw.split(","):
        provider, sep, model = item.strip().partition("/")
        if not sep or provider not in PROVIDERS or not _MODEL.fullmatch(model):
            raise ConfigError(f"{ALLOWLIST_VAR} entries must be gemini/<model> or groq/<model>")
        entries.append((provider, model))
    if len(set(entries)) != len(entries):
        raise ConfigError(f"{ALLOWLIST_VAR} holds duplicate entries")
    return frozenset(entries)


def load_eval_config(provider: str, model: str, env: Mapping[str, str] | None = None) -> EvalConfig:
    """Resolve one explicitly requested provider/model; it must be allowlisted and have its own credential."""
    env = os.environ if env is None else env
    allowed = parse_allowlist(env.get(ALLOWLIST_VAR))
    if (provider, model) not in allowed:
        raise ConfigError("requested provider/model is not in the eval allowlist")
    key = (env.get(_key_var(provider)) or "").strip()
    if not key:
        raise ConfigError(f"{_key_var(provider)} is not set")
    return EvalConfig(provider, model, key)
