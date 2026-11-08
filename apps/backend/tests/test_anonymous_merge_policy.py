"""Canonical, container-free refusal rules for the bounded anonymous event merge."""
from datetime import datetime, timedelta, timezone

import pytest

from identity.merge import MergeRejected, validate_candidate

NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)


def test_recent_unowned_events_are_eligible():
    validate_candidate([(None, NOW - timedelta(minutes=1))], NOW)


@pytest.mark.parametrize("events,reason", [
    ([], "empty"),
    ([(None, NOW - timedelta(days=2))], "stale"),
    ([(None, NOW + timedelta(minutes=1))], "stale"),
    ([("other-customer", NOW)], "ownership_conflict"),
    ([(None, NOW)] * 101, "too_many_events"),
])
def test_ambiguous_anonymous_state_is_refused(events, reason):
    with pytest.raises(MergeRejected, match=reason):
        validate_candidate(events, NOW)
