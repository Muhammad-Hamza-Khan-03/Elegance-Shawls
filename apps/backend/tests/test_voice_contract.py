from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice.contract import FakeVoiceProvider, PrivacyPolicy, VoiceInput, VoiceOutcome
from voice.evaluation import evaluate_cases, release_gate
from voice.normalization import normalize_transcript, parse_intent


def test_urdu_and_roman_transcripts_normalize_to_same_price_intent():
    assert parse_intent(normalize_transcript("مجھے یہ دوپٹہ ۲،۵۰۰ روپے کا چاہیے")).price_pkr == 2500
    assert parse_intent(normalize_transcript("mujhe yeh dupatta 2,500 rupay ka chahiye")).price_pkr == 2500


def test_negation_is_explicit_and_fail_closed():
    parsed = parse_intent(normalize_transcript("mujhe black shawl nahi chahiye"))
    assert parsed.negated is True
    assert parsed.outcome is VoiceOutcome.NEGATED
    uncertain = parse_intent(normalize_transcript("shayad 2500 ya 3000 rupay"))
    assert uncertain.outcome is VoiceOutcome.AMBIGUOUS
    assert uncertain.needs_review is True


def test_fake_provider_is_offline_and_audio_is_not_retained(monkeypatch):
    import socket

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network forbidden")))
    result = FakeVoiceProvider({"clip-1": "nahi, 2500 PKR nahi chahiye"}).transcribe(
        VoiceInput(audio_id="clip-1", audio_bytes=b"synthetic", provenance="synthetic")
    )
    assert result.transcript.startswith("nahi")
    assert result.audio_persisted is False
    assert result.privacy.raw_audio_retained is False


def test_scoring_is_exactly_price_and_negation():
    result = evaluate_cases([
        {"id": "a", "transcript": "2500 PKR chahiye", "expected_price_pkr": 2500, "expected_negated": False},
        {"id": "b", "transcript": "2500 PKR nahi chahiye", "expected_price_pkr": 2500, "expected_negated": True},
    ])
    assert result.price_accuracy == 1.0
    assert result.negation_accuracy == 1.0
    assert result.score == 1.0
    assert result.wer_used is False


def test_release_gate_blocks_empty_unreviewed_and_failed():
    assert release_gate([]).ready is False
    assert release_gate([{"reviewed": False, "passed": True}]).ready is False
    assert release_gate([{"reviewed": True, "passed": False}]).ready is False
    assert release_gate([{"reviewed": True, "passed": True}]).ready is True


def test_provenance_and_privacy_are_required():
    voice_input = VoiceInput(audio_id="synthetic-1", provenance="synthetic", privacy=PrivacyPolicy())
    assert voice_input.provenance == "synthetic"
    assert voice_input.privacy.raw_audio_retained is False
