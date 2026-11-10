from datetime import datetime, timezone, timedelta

from memory.queue_guard import ExtractionJob, accept_result

T0 = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def job():
    return ExtractionJob("synthetic-customer", 4, T0, "style")


def test_current_queued_work_is_accepted_only_when_feature_is_explicitly_enabled():
    assert not accept_result(job(), current_memory_version=4, memory_enabled=False, tombstone_at=None, now=T0)
    assert accept_result(job(), current_memory_version=4, memory_enabled=True, tombstone_at=None, now=T0 + timedelta(seconds=1))


def test_delete_bumps_memory_version_and_rejects_replay_retry_and_restart():
    for delivery in ("replay", "retry", "worker-restart"):
        assert not accept_result(job(), current_memory_version=5, memory_enabled=True, tombstone_at=T0, now=T0 + timedelta(seconds=2)), delivery


def test_disable_rejects_even_when_version_and_tombstone_are_unchanged():
    assert not accept_result(job(), current_memory_version=4, memory_enabled=False, tombstone_at=None, now=T0 + timedelta(seconds=1))


def test_newer_work_after_tombstone_is_not_silently_relaxed():
    newer = ExtractionJob("synthetic-customer", 5, T0 + timedelta(seconds=1), "style")
    assert accept_result(newer, current_memory_version=5, memory_enabled=True, tombstone_at=T0, now=T0 + timedelta(seconds=2))
    assert not accept_result(newer, current_memory_version=5, memory_enabled=True, tombstone_at=T0 + timedelta(seconds=1), now=T0 + timedelta(seconds=2))
