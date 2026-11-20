from fastapi import FastAPI
from fastapi.testclient import TestClient

from observability import errors
from observability.request_log import RequestLogMiddleware


def _client():
    app = FastAPI()
    app.add_middleware(RequestLogMiddleware)

    @app.get("/items/{item_id}")
    def boom(item_id: str):
        raise ValueError("secret@example.com 0300-1234567")

    return TestClient(app, raise_server_exceptions=False)


def test_noop_without_reporter():
    errors.set_reporter(None)
    assert _client().get("/items/abc").status_code == 500


def test_report_has_identifiers_but_no_message_or_query():
    seen = []
    errors.set_reporter(seen.append)
    try:
        r = _client().get("/items/abc?token=hunter2", headers={"x-request-id": "req-12345678"})
    finally:
        errors.set_reporter(None)
    assert r.status_code == 500
    assert seen == [{"request_id": "req-12345678", "route": "/items/{item_id}", "status": 500,
                     "exception_type": "ValueError", "release": "unknown"}]
    assert "secret" not in str(seen) and "hunter2" not in str(seen)


def test_broken_reporter_does_not_change_response():
    def bad(_):
        raise RuntimeError("down")
    errors.set_reporter(bad)
    try:
        assert _client().get("/items/abc").status_code == 500
    finally:
        errors.set_reporter(None)
