import json
import logging

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


def test_access_log_has_request_id_and_no_secrets(monkeypatch):
    records = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    logging.getLogger("elegance.access").addHandler(handler)

    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 120)
    monkeypatch.setattr(settings, "admin_rate_limit_per_minute", 60)
    monkeypatch.setattr(settings, "admin_api_key", "")
    client = TestClient(main.create_app())

    supplied = client.get("/health/", headers={"X-Request-ID": "req-12345678"})
    assert supplied.headers["x-request-id"] == "req-12345678"
    generated = client.get("/health/?token=private-query", headers={"X-Request-ID": "bad id!"})
    assert len(generated.headers["x-request-id"]) == 32
    client.post("/products/admin/", headers={"X-Admin-Key": "private-admin-key"}, json={"name": "secret body"})

    logging.getLogger("elegance.access").removeHandler(handler)
    lines = [json.loads(record) for record in records]
    assert [(line["path"], line["status"]) for line in lines] == [
        ("/health/", 200), ("/health/", 200), ("/products/admin/", 503),
    ]
    assert lines[0]["request_id"] == "req-12345678"
    text = json.dumps(lines)
    for private in ("private-query", "private-admin-key", "secret body"):
        assert private not in text



def test_internal_token_exempts_only_public_reads(monkeypatch):
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1)
    monkeypatch.setattr(settings, "admin_rate_limit_per_minute", 1)
    monkeypatch.setattr(settings, "internal_api_token", "internal-token-fixture")
    monkeypatch.setattr(settings, "admin_api_key", "")
    client = TestClient(main.create_app())
    internal = {"X-Internal-API-Token": "internal-token-fixture"}

    for _ in range(5):
        assert client.get("/health/", headers=internal).status_code == 200
    assert client.get("/health/").status_code == 200
    assert client.get("/health/").status_code == 429
    assert client.get("/health/", headers={"X-Internal-API-Token": "wrong"}).status_code == 429

    assert client.post("/products/admin/", headers=internal, json={}).status_code == 503
    assert client.post("/products/admin/", headers=internal, json={}).status_code == 429


def test_internal_token_is_ignored_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1)
    monkeypatch.setattr(settings, "internal_api_token", "")
    client = TestClient(main.create_app())
    assert client.get("/health/", headers={"X-Internal-API-Token": ""}).status_code == 200
    assert client.get("/health/", headers={"X-Internal-API-Token": ""}).status_code == 429
