from datetime import datetime, timedelta, timezone

from whatsapp.monitoring import Snapshot, evaluate, prometheus

NOW = datetime(2026, 11, 6, 14, 0, tzinfo=timezone.utc)


def snap(**over):
    return Snapshot(**{"now": NOW, "state": "connected", "state_since": NOW - timedelta(hours=1), **over})


def test_healthy_has_no_alerts():
    assert evaluate(snap(lag=0, dead=0)) == []


def test_needs_pairing_alerts_immediately():
    assert evaluate(snap(state="needs_pairing", state_since=NOW))[0].startswith("needs_pairing")


def test_disconnected_only_after_ten_minutes_or_unknown_since():
    assert evaluate(snap(state="connecting", state_since=NOW - timedelta(minutes=9))) == []
    assert evaluate(snap(state="connecting", state_since=NOW - timedelta(minutes=11)))[0].startswith("disconnected")
    assert evaluate(snap(state="unreachable", state_since=None))[0].startswith("disconnected")


def test_lag_and_dead_letters():
    assert evaluate(snap(lag=500)) == []
    alerts = evaluate(snap(lag=501, dead=2))
    assert [a.split(":")[0] for a in alerts] == ["consumer_lag", "dead_letters"]
    assert evaluate(snap(lag=None, dead=None)) == []        # unknown is not an alert


def test_prometheus_text_skips_unknowns():
    text = prometheus(snap(lag=3, median_contact_seconds=None, linked_by_reference=4, alerts=["x"]))
    assert "whatsapp_bridge_connected 1\n" in text and "whatsapp_consumer_lag 3\n" in text
    assert 'whatsapp_enquiries_linked{source="reference"} 4\n' in text
    assert "dead_letters" not in text and "median" not in text and "whatsapp_alerts_firing 1\n" in text
