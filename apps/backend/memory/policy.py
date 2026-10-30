"""M4-S1 memory policy: content minimization and the deterministic provider gate. Pure functions, no I/O, no model calls.

Every ambiguity resolves to the refusing answer: unknown or malformed provider declarations deny, text that looks like contact or
identity data is rejected, and nothing here infers or suggests memory (`reason` is stored, never generated).
"""
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from configuration.config import settings
from llm.gateway import provider_of

MEMORY_POLICY_VERSION = "2026-10-30"   # bump when what is stored or how long changes; consent records the version it was given under
DEFAULT_RETENTION_DAYS, MAX_RETENTION_DAYS = 180, 365
TOMBSTONE_DAYS = 30                    # how long a content-free tombstone keeps a deleted create from being replayed
MAX_ACTIVE_ITEMS = 50
MAX_TEXT = 200

KEY_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
IDEMPOTENCY_PATTERN = r"^idem_[A-Za-z0-9_-]{16,64}$"   # same shape as assistant action keys
SOURCE_REF_PATTERN = r"^[A-Za-z0-9_.:-]{1,64}$"

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")
_LONG_NUMBER = re.compile(r"(?:\d[\s().+-]*){7,}")   # phone, card or national-id shaped digit runs


def clean_text(value: str) -> str:
    """Strip, then reject empty, over-long, control/format characters, and contact- or identity-shaped content (data minimization).
    shortcut: a regex screen, not PII detection; a miss is still the customer's own explicit, deletable text."""
    value = unicodedata.normalize("NFC", value).strip()
    if not 1 <= len(value) <= MAX_TEXT:
        raise ValueError(f"must be 1-{MAX_TEXT} characters")
    if any(unicodedata.category(ch) in {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"} for ch in value):
        raise ValueError("must not contain control or unassigned characters")
    if _EMAIL.search(value) or _LONG_NUMBER.search(value):
        raise ValueError("must not contain contact or identity details")
    return value


# ---- provider gate ------------------------------------------------------------------------------------------------
class TrainingPolicy(str, Enum):
    NO_TRAINING = "no_training"
    SELF_HOSTED = "self_hosted"
    OPT_OUT = "opt_out"      # trains unless an account-level opt-out is set; that cannot be verified here, so it is denied
    MAY_TRAIN = "may_train"
    UNKNOWN = "unknown"


ALLOWED_POLICIES = frozenset({TrainingPolicy.NO_TRAINING, TrainingPolicy.SELF_HOSTED})


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str                      # fixed code, safe to log
    denied_models: tuple[str, ...] = ()


def _declared(raw: str) -> dict[str, TrainingPolicy]:
    """'groq=may_train,acme=no_training' -> {provider: policy}. A malformed entry, an unknown policy name or a provider declared
    twice with different policies becomes UNKNOWN for that provider, never a permissive default."""
    out: dict[str, TrainingPolicy] = {}
    for entry in (raw or "").split(","):
        if not entry.strip():
            continue
        name, _, policy = entry.partition("=")
        name = name.strip().lower()
        if not name:
            continue
        try:
            parsed = TrainingPolicy(policy.strip().lower())
        except ValueError:
            parsed = TrainingPolicy.UNKNOWN
        out[name] = parsed if out.get(name, parsed) == parsed else TrainingPolicy.UNKNOWN
    return out


def classify(model: object, declared: str, free_tier: str) -> TrainingPolicy:
    if not isinstance(model, str) or "/" not in model.strip():
        return TrainingPolicy.UNKNOWN                     # a bare or non-string model name carries no provider to vouch for
    provider = provider_of(model.strip())
    if provider in {p.strip().lower() for p in (free_tier or "").split(",") if p.strip()}:
        return TrainingPolicy.MAY_TRAIN                   # a free-tier listing beats any allowing declaration
    return _declared(declared).get(provider, TrainingPolicy.UNKNOWN)


def provider_gate(models: Iterable[object], declared: str | None = None, free_tier: str | None = None) -> GateDecision:
    """Allowed only when there is at least one model and EVERY model in the chain (fallbacks included) is explicitly
    no-training or self-hosted. Same inputs, same answer."""
    declared = settings.llm_provider_training_policies if declared is None else declared
    free_tier = settings.llm_free_tier_providers if free_tier is None else free_tier
    models = tuple(models)
    if not models:
        return GateDecision(False, "no_model")
    denied = tuple(str(m) for m in models if classify(m, declared, free_tier) not in ALLOWED_POLICIES)
    return GateDecision(False, "provider_not_cleared", denied) if denied else GateDecision(True, "cleared")


def authorize_model_use(consented: bool, models: Iterable[object], declared: str | None = None, free_tier: str | None = None) -> GateDecision:
    """The only question later slices may ask before a model sees customer memory: consent first, then the provider gate."""
    if consented is not True:
        return GateDecision(False, "consent_required")
    return provider_gate(models, declared, free_tier)
