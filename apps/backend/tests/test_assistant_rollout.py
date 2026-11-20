import pytest

from assistant.grounded import in_rollout
from configuration.config import settings


@pytest.mark.parametrize("percent,expected", [(0, 0), (100, 1000)])
def test_extremes(monkeypatch, percent, expected):
    monkeypatch.setattr(settings, "assistant_rollout_percent", percent)
    assert sum(in_rollout(f"sess-{i}") for i in range(1000)) == expected


def test_partial_is_roughly_proportional_and_sticky(monkeypatch):
    monkeypatch.setattr(settings, "assistant_rollout_percent", 30)
    ids = [f"sess-{i}" for i in range(2000)]
    first = [in_rollout(i) for i in ids]
    assert 0.25 < sum(first) / len(ids) < 0.35
    assert first == [in_rollout(i) for i in ids]


def test_raising_the_percentage_never_removes_a_session(monkeypatch):
    ids = [f"sess-{i}" for i in range(500)]
    monkeypatch.setattr(settings, "assistant_rollout_percent", 20)
    low = {i for i in ids if in_rollout(i)}
    monkeypatch.setattr(settings, "assistant_rollout_percent", 50)
    assert low <= {i for i in ids if in_rollout(i)}
