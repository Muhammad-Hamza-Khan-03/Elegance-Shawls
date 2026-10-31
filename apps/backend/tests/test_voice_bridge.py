import socket

from actions.kernel import ActionContext, ActionProposal, IdempotencyLedger
from voice.bridge import bridge_voice_result, bridge_voice_transcript, validate_voice_proposal
from voice.contract import PrivacyPolicy, VoiceOutcome, VoiceResult


def test_text_urdu_and_roman_urdu_share_the_canonical_query_handoff():
    text = bridge_voice_transcript("brown shawl under 4000")
    roman = bridge_voice_transcript("bhoora shawal 4000 se kam")
    urdu = bridge_voice_transcript("بھورا شال ۴۰۰۰ سے کم")
    assert all(not r.needs_review for r in (text, roman, urdu))
    assert [(r.intent.colour, r.intent.max_price, r.intent.terms, r.handoff) for r in (text, roman, urdu)] == [
        ("brown", 4000, ("shawl",), text.handoff),
    ] * 3


def test_uncertain_or_negated_voice_is_reviewed_before_search_or_action():
    for result in (
        bridge_voice_transcript("shayad 2500 ya 3000 rupay"),
        bridge_voice_transcript("black shawl nahi chahiye"),
    ):
        assert result.needs_review is True
        assert result.handoff is None
        assert result.action_allowed is False
        assert result.provenance.audio_persisted is False


def test_contradictory_price_fails_closed_even_when_voice_result_claims_accepted():
    base = bridge_voice_transcript("under 5000 over 6000")
    result = VoiceResult(
        transcript=base.intent.raw,
        normalized_transcript=base.intent.normalized,
        outcome=VoiceOutcome.ACCEPTED,
        price_pkr=None,
        negated=False,
        confidence=0.99,
        needs_review=False,
        provenance="eval:contradiction",
        privacy=PrivacyPolicy(),
    )
    bridged = bridge_voice_result(result)
    assert bridged.needs_review and bridged.handoff is None
    assert "contradictory_price" in bridged.reasons


def test_provenance_is_structured_hashed_and_contains_no_raw_input_or_audio():
    text = "brown shawl under 4000"
    result = bridge_voice_transcript(text, provenance="eval:urdu-v1", evaluation="urdu-v1")
    data = result.as_dict()
    assert data["provenance"]["evaluation"] == "urdu-v1"
    assert len(data["provenance"]["input_hash"]) == 64
    assert data["provenance"]["provider_policy"] == "provider-neutral/offline-only"
    assert text not in str(data["provenance"])
    assert "audio_bytes" not in str(data["provenance"])


def test_review_gate_calls_same_kernel_only_after_review_gate_and_never_executes(monkeypatch):
    result = bridge_voice_transcript("black shawl nahi chahiye")
    proposal = ActionProposal("add_to_cart", "idem_0123456789abcdef", {}, ActionContext("sess-1", {"cart:propose"}))
    calls = []
    monkeypatch.setattr("voice.bridge.validate", lambda *args: calls.append(args) or None)
    decision = validate_voice_proposal(result, proposal, object(), IdempotencyLedger())
    assert decision.outcome == "rejected" and decision.reason == "voice_needs_review" and decision.executed is False
    assert calls == []


def test_voice_bridge_import_and_execution_are_offline(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("network/provider call")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    assert bridge_voice_transcript("safaid stole 4500 se kam").intent.colour == "white"


def test_caller_provenance_is_never_echoed_into_output():
    raw = "call 0300-1234567 about brown shawl"
    for prov in (raw, "transcript", "eval:" + raw):
        data = bridge_voice_transcript(raw, provenance=prov).as_dict()
        assert raw not in str(data["provenance"]) and "0300" not in str(data["provenance"])
        assert data["provenance"]["source"] == "voice_text_bridge"
        assert data["provenance"]["evaluation"] is None
    assert bridge_voice_transcript("a b", evaluation="urdu-v1").as_dict()["provenance"]["evaluation"] == "urdu-v1"


def test_malformed_public_inputs_fail_closed_without_raising():
    for bad in (None, 5, 1.5, {"q": "x"}, ["a"], b"shawl", object()):
        out = bridge_voice_transcript(bad)
        assert out.needs_review and out.handoff is None and not out.action_allowed
        assert "invalid_transcript" in out.reasons
        assert out.as_dict()["provenance"]["outcome"] == "uncertain"
    # invalid nested/hostile optional args also fail closed
    out = bridge_voice_transcript("brown shawl", provenance={"x": 1}, evaluation=["y"])
    assert out.as_dict()["provenance"]["source"] == "voice_text_bridge"
    assert out.as_dict()["provenance"]["evaluation"] is None
