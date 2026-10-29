"""Pure ingestion-model rules (no database): content hashing and the staged status state machine."""
from models.ingestion_model import content_hash
from schemas.ingestion_schema import STAGED_TRANSITIONS, StagedStatus, can_transition


def test_content_hash_is_stable_and_change_sensitive():
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})
    assert content_hash({"a": 1}) != content_hash({"a": 2})


def test_staged_cannot_skip_to_published():
    assert not can_transition(StagedStatus.PENDING_REVIEW, StagedStatus.PUBLISHED)
    assert not can_transition(StagedStatus.REJECTED, StagedStatus.PUBLISHED)
    assert can_transition(StagedStatus.APPROVED, StagedStatus.PUBLISHED)
    assert STAGED_TRANSITIONS[StagedStatus.ARCHIVED] == set()


def test_every_status_has_a_transition_entry_and_only_reaches_known_statuses():
    assert set(STAGED_TRANSITIONS) == set(StagedStatus)
    assert all(targets <= set(StagedStatus) for targets in STAGED_TRANSITIONS.values())
