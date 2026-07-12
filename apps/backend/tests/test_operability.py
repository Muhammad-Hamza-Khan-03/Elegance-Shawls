from fastapi.testclient import TestClient

import main
from configuration.config import settings


def test_rate_limit_returns_retry_after(monkeypatch):
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1)
    client = TestClient(main.create_app())
    assert client.get("/health/").status_code == 200
    limited = client.get("/health/")
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"


def test_readiness_reports_database_state(monkeypatch):
    async def unavailable():
        return False

    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 120)
    monkeypatch.setattr(main, "database_is_ready", unavailable)
    response = TestClient(main.create_app()).get("/ready/")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
