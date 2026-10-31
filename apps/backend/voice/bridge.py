"""Provider-neutral bridge from an already-normalized voice result to text safety paths.

This module deliberately does not accept audio, call ASR/providers, persist anything, or execute actions.
Voice is only provenance around the canonical deterministic text parser and M3 action kernel.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from typing import Any

from actions.kernel import ActionProposal, CatalogueState, Decision, IdempotencyLedger, validate
from semantic.query_parser import Handoff, QueryIntent, handoff, parse_query

from .contract import PrivacyPolicy, VoiceOutcome, VoiceResult

BRIDGE_VERSION = 1
SOURCE = "voice_text_bridge"
_EVAL_ID = re.compile(r"eval:([a-z0-9][a-z0-9._-]{0,31})")


@dataclass(frozen=True)
class VoiceProvenance:
    """Audit-safe voice metadata; no raw audio or transcript is included."""

    input_hash: str
    source: str
    outcome: str
    confidence: float
    evaluation: str | None
    provider_policy: str
    audio_persisted: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": BRIDGE_VERSION,
            "input_hash": self.input_hash,
            "source": self.source,
            "outcome": self.outcome,
            "confidence": self.confidence,
            "evaluation": self.evaluation,
            "provider_policy": self.provider_policy,
            "audio_persisted": self.audio_persisted,
        }


@dataclass(frozen=True)
class VoiceBridgeResult:
    intent: QueryIntent
    handoff: Handoff | None
    needs_review: bool
    reasons: tuple[str, ...]
    provenance: VoiceProvenance

    @property
    def action_allowed(self) -> bool:
        """False for every voice result: this bridge never confirms or executes an action."""
        return False

    def as_dict(self) -> dict[str, Any]:
        return {
            "normalized_query": self.intent.normalized,
            "language": self.intent.language,
            "needs_review": self.needs_review,
            "reasons": list(self.reasons),
            "provenance": self.provenance.as_dict(),
            "handoff": None if self.handoff is None else {"q": self.handoff.q, "variant": self.handoff.variant.__dict__},
            "action_allowed": False,
        }


def _provenance(result: VoiceResult) -> VoiceProvenance:
    # Hash the normalized transcript only; never expose or retain raw audio/transcript in provenance.
    digest = hashlib.sha256(result.normalized_transcript.encode("utf-8")).hexdigest()
    # Caller-supplied provenance is untrusted: emit a fixed source and only a strict evaluation slug.
    match = _EVAL_ID.fullmatch(result.provenance) if isinstance(result.provenance, str) else None
    source = SOURCE
    evaluation = match.group(1) if match else None
    return VoiceProvenance(
        input_hash=digest,
        source=source,
        outcome=result.outcome.value,
        confidence=result.confidence,
        evaluation=evaluation,
        provider_policy="provider-neutral/offline-only",
        audio_persisted=result.audio_persisted or result.privacy.raw_audio_retained,
    )


def bridge_voice_result(result: VoiceResult) -> VoiceBridgeResult:
    """Parse voice through the exact text parser and fail closed on voice uncertainty/negation.

    The normalized transcript is the only input to ``parse_query``. Even if that parser would accept it,
    a VoiceResult marked uncertain, ambiguous, negated, or needs_review cannot produce a search handoff.
    """
    intent = parse_query(result.normalized_transcript)
    reasons = list(intent.reasons)
    if result.needs_review or result.outcome is not VoiceOutcome.ACCEPTED or result.audio_persisted or result.privacy.raw_audio_retained:
        if result.audio_persisted or result.privacy.raw_audio_retained:
            reasons.append("audio_persistence_forbidden")
        if result.outcome is VoiceOutcome.NEGATED and "voice_negation" not in reasons:
            reasons.append("voice_negation")
        elif result.outcome is VoiceOutcome.AMBIGUOUS and "voice_ambiguous" not in reasons:
            reasons.append("voice_ambiguous")
        elif result.outcome is VoiceOutcome.UNCERTAIN and "voice_uncertain" not in reasons:
            reasons.append("voice_uncertain")
        elif result.needs_review and "voice_needs_review" not in reasons:
            reasons.append("voice_needs_review")
    review = bool(reasons)
    return VoiceBridgeResult(
        intent=intent,
        handoff=None if review else handoff(intent),
        needs_review=review,
        reasons=tuple(reasons),
        provenance=_provenance(result),
    )


def bridge_voice_transcript(transcript: str, *, provenance: str = "transcript", evaluation: str | None = None) -> VoiceBridgeResult:
    """Convenience seam for tests/callers that already have normalized transcript text, never audio."""
    from .normalization import normalize_transcript, parse_intent

    if type(transcript) is not str:
        # Public boundary: anything but plain text fails closed instead of raising.
        failed = bridge_voice_result(VoiceResult(
            transcript="", normalized_transcript="", outcome=VoiceOutcome.UNCERTAIN, price_pkr=None,
            negated=None, confidence=0.0, needs_review=True, provenance="", privacy=PrivacyPolicy(),
        ))
        return replace(failed, reasons=(*failed.reasons, "invalid_transcript"))
    normalized = normalize_transcript(transcript)
    parsed = parse_intent(normalized)
    source = f"eval:{evaluation}" if isinstance(evaluation, str) and evaluation else provenance
    return bridge_voice_result(VoiceResult(
        transcript=transcript,
        normalized_transcript=normalized,
        outcome=parsed.outcome,
        price_pkr=parsed.price_pkr,
        negated=parsed.negated,
        confidence=parsed.confidence,
        needs_review=parsed.needs_review,
        provenance=source,
        privacy=PrivacyPolicy(),
    ))


def validate_voice_proposal(
    result: VoiceBridgeResult,
    proposal: ActionProposal,
    state: CatalogueState,
    ledger: IdempotencyLedger,
) -> Decision:
    """Gate a voice-originated proposal before the unchanged M3 kernel; never execute it."""
    if result.needs_review or result.handoff is None:
        return Decision("rejected", "voice_needs_review", "unknown", executed=False)
    return validate(proposal, state, ledger)
