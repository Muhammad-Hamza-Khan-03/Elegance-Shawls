"""Container-free checks of the admin account primitives and of route coverage."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from configuration.config import settings
from main import create_app
from schemas.admin_schema import AccountResponse, AuditEntryResponse, SessionResponse
from security import admin_auth
from security.admin_auth import LEGACY_PERMISSIONS, ROLE_PERMISSIONS, legacy_key_enabled
from security.passwords import (
    MIN_PASSWORD_LENGTH, hash_password, hash_session_token, new_session_token, password_problem, verify_password,
)
from tests.admin_stub import open_legacy_admin

PASSWORD = "correct horse battery"


def test_password_hash_is_salted_slow_and_verifiable():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second and PASSWORD not in first and first.startswith("scrypt$")
    assert verify_password(PASSWORD, first) and not verify_password(PASSWORD + "x", first)


@pytest.mark.parametrize("stored", ["", "garbage", "scrypt$a$b$c$d$e", "bcrypt$1$2$3$4$5", "scrypt$16384$8$1$!!$!!"])
def test_a_malformed_stored_hash_is_a_failed_login_not_an_error(stored):
    assert verify_password(PASSWORD, stored) is False


def test_password_policy():
    assert password_problem(PASSWORD, "a@b.co") is None
    assert password_problem("short", "a@b.co")
    assert password_problem("x" * 257, "a@b.co")
    assert password_problem("owner@example.com", "owner@example.com")
    assert password_problem("  Owner  ", "owner@example.com") is None or len("  Owner  ") < MIN_PASSWORD_LENGTH


def test_session_tokens_are_unguessable_and_only_their_hash_is_stored():
    token, digest = new_session_token()
    other, _ = new_session_token()
    assert token != other and len(token) > 40 and token not in digest
    assert digest == hash_session_token(token) and len(digest) == 64


def test_no_response_model_can_carry_a_credential_hash():
    forbidden = {"password_hash", "token_hash", "failed_login_count", "locked_until"}
    for model in (AccountResponse, AuditEntryResponse):
        assert not forbidden & set(model.model_fields)
    assert set(SessionResponse.model_fields) == {"token", "expires_at", "account"}   # returned to the Next.js server only


@pytest.mark.parametrize("expires,enabled", [
    ("", False),
    ("not a date", False),
    ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), False),
    (datetime.now().replace(tzinfo=None).isoformat(), False),                       # ambiguous without an offset
    ((datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), True),
])
def test_legacy_key_is_off_unless_a_future_expiry_is_set(monkeypatch, expires, enabled):
    monkeypatch.setattr(settings, "admin_api_key", "k" * 40)
    monkeypatch.setattr(settings, "admin_legacy_key_expires_at", expires)
    assert legacy_key_enabled() is enabled
    monkeypatch.setattr(settings, "admin_api_key", "")
    assert legacy_key_enabled() is False


def test_the_permission_matrix_is_least_privilege():
    viewer, editor, owner = (ROLE_PERMISSIONS[r] for r in ("viewer", "editor", "owner"))
    assert admin_auth.CATALOGUE_WRITE not in viewer and admin_auth.CATALOGUE_READ in viewer
    assert admin_auth.CATALOGUE_WRITE in editor
    assert not {admin_auth.ACCOUNTS_MANAGE, admin_auth.AUDIT_READ, admin_auth.PLATFORM_OPERATE} & editor
    assert viewer < editor < owner
    assert not {admin_auth.ACCOUNTS_MANAGE, admin_auth.AUDIT_READ} & LEGACY_PERMISSIONS
    assert admin_auth.Principal("owner-ish-unknown").permissions == frozenset()      # unknown role: nothing


def test_every_admin_route_rejects_anonymous_callers(monkeypatch):
    """Default deny: a new /products/admin or /v1/admin route that forgets the guard answers something other than 401 here."""
    app = open_legacy_admin(create_app(), monkeypatch, "k" * 40)
    client = TestClient(app)
    open_routes = {("/v1/admin/auth/login", "post")}
    checked = 0
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith(("/products/admin", "/v1/admin", "/v1/llm")):
            continue
        for method in operations:
            if (path, method) in open_routes:
                continue
            checked += 1
            url = path.replace("{", "").replace("}", "")      # any value: the guard answers before the handler runs
            assert client.request(method.upper(), url).status_code == 401, (method, path)
    assert checked >= 20


def test_unauthenticated_and_unknown_credentials_get_401_without_touching_the_database(monkeypatch):
    client = TestClient(open_legacy_admin(create_app(), monkeypatch, "legacy-key-" + "x" * 30))
    assert client.get("/products/admin/").status_code == 401
    assert client.post("/products/admin/", json={}).status_code == 401
    assert client.get("/products/admin/", headers={"X-Admin-Key": "wrong"}).status_code == 401


def test_the_legacy_key_cannot_manage_identities_or_read_the_audit_log(monkeypatch):
    key = "legacy-key-" + "x" * 30
    client = TestClient(open_legacy_admin(create_app(), monkeypatch, key))
    for method, path in (("get", "/v1/admin/accounts"), ("get", "/v1/admin/audit"), ("post", "/v1/admin/accounts")):
        assert getattr(client, method)(path, headers={"X-Admin-Key": key}).status_code == 403, path
    assert client.get("/v1/admin/auth/me", headers={"X-Admin-Key": key}).json()["legacy"] is True
