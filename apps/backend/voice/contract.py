"""Provider-neutral, side-effect-free voice contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class VoiceOutcome(StrEnum):
    ACCEPTED = "accepted"
    NEGATED = "negated"
    AMBIGUOUS = "ambiguous"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class PrivacyPolicy:
    raw_audio_retained: bool = False
    retention_seconds: int = 0
    customer_data_allowed: bool = False


@dataclass(frozen=True)
class VoiceInput:
    audio_id: str | None = None
    audio_bytes: bytes | None = None  # transient input only; never persisted by this contract
    transcript: str | None = None
    provenance: str = "unknown"
    privacy: PrivacyPolicy = field(default_factory=PrivacyPolicy)


@dataclass(frozen=True)
class VoiceResult:
    transcript: str
    normalized_transcript: str
    outcome: VoiceOutcome
    price_pkr: int | None
    negated: bool | None
    confidence: float
    needs_review: bool
    provenance: str
    privacy: PrivacyPolicy
    audio_persisted: bool = False


class VoiceProvider(Protocol):
    def transcribe(self, voice_input: VoiceInput) -> VoiceResult: ...


class FakeVoiceProvider:
    """Offline seam for tests; maps IDs to transcripts and never handles network/audio storage."""

    def __init__(self, transcripts: dict[str, str]):
        self._transcripts = dict(transcripts)

    def transcribe(self, voice_input: VoiceInput) -> VoiceResult:
        from .normalization import normalize_transcript, parse_intent

        transcript = voice_input.transcript or self._transcripts.get(voice_input.audio_id or "", "")
        parsed = parse_intent(normalize_transcript(transcript))
        return VoiceResult(
            transcript=transcript,
            normalized_transcript=parsed.normalized_transcript,
            outcome=parsed.outcome,
            price_pkr=parsed.price_pkr,
            negated=parsed.negated,
            confidence=parsed.confidence,
            needs_review=parsed.needs_review,
            provenance=voice_input.provenance,
            privacy=voice_input.privacy,
        )
