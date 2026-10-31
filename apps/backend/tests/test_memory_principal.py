"""M4-S2 container-free tests: the customer principal/session seam is fail-closed and never reads identity from the client."""
import hashlib
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from memory.principal import SESSION_HEADER, CustomerPrincipal, get_session_verifier
from routes.memory_routes import memory_customer, router

NOW = datetime.now(timezone.utc)
CUSTOMER = uuid.uuid4()
TOKEN = "cs1.valid-token"
OTHER = "cs1.other-token"


def sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def principal(**over) -> CustomerPrincipal:
    return replace(CustomerPrincipal(CUSTOMER, "sess-1", sha(TOKEN), NOW + timedelta(hours=1)), **over)


class FakeVerifier:
    def __init__(self, result=None, error=False):
        self.result, self.error, self.seen = result, error, []

    async def verify(self, token, now):
        self.seen.append(token)
        if self.error:
            raise RuntimeError("store down")
        return self.result


def client_for(verifier) -> TestClient:
    app = FastAPI()

    @app.get("/who")
    async def who(customer: uuid.UUID = Depends(memory_customer)):
        return {"customer": str(customer)}

    app.dependency_overrides[get_session_verifier] = lambda: verifier
    return TestClient(app)


def call(verifier, token=TOKEN, **headers):
    h = dict(headers)
    if token is not None:
        h[SESSION_HEADER] = token
    return client_for(verifier).get("/who", headers=h)


def test_valid_principal_resolves_to_its_customer():
    r = call(FakeVerifier(principal()))
    assert r.status_code == 200 and r.json() == {"customer": str(CUSTOMER)}


def test_no_verifier_installed_is_401_even_with_a_token():
    assert call(None).status_code == 401
    assert TestClient(_default_app()).get("/who", headers={SESSION_HEADER: TOKEN}).status_code == 401


def _default_app() -> FastAPI:
    app = FastAPI()

    @app.get("/who")
    async def who(customer: uuid.UUID = Depends(memory_customer)):
        return {}

    return app


@pytest.mark.parametrize("name,verifier,token", [
    ("absent token", FakeVerifier(principal()), None),
    ("empty token", FakeVerifier(principal()), ""),
    ("oversized token", FakeVerifier(principal()), "x" * 600),
    ("unknown session", FakeVerifier(None), TOKEN),
    ("expired", FakeVerifier(principal(expires_at=NOW - timedelta(seconds=1))), TOKEN),
    ("naive expiry", FakeVerifier(principal(expires_at=datetime.now())), TOKEN),
    ("bound to another token", FakeVerifier(principal()), OTHER),
    ("blank session id", FakeVerifier(principal(session_id="")), TOKEN),
    ("non-uuid customer", FakeVerifier(principal(customer_id="not-a-uuid")), TOKEN),
    ("verifier error", FakeVerifier(error=True), TOKEN),
    ("wrong result type", FakeVerifier({"customer_id": str(CUSTOMER)}), TOKEN),
])
def test_bad_principal_is_an_identical_401(name, verifier, token):
    r = call(verifier, token)
    assert r.status_code == 401 and r.json() == {"detail": "Customer authentication is required"}, name
    assert r.headers["www-authenticate"] == "Session"


def test_client_supplied_identity_is_ignored_and_never_echoed():
    other = uuid.uuid4()
    v = FakeVerifier(principal())
    r = client_for(v).get(f"/who?customer_id={other}&user_id={other}", headers={
        SESSION_HEADER: TOKEN, "X-Customer-Id": str(other), "X-Admin-Key": "k", "X-Admin-Session": "es1.x", "Cookie": f"customer_id={other}"})
    assert r.json() == {"customer": str(CUSTOMER)}
    assert v.seen == [TOKEN]  # only the opaque token reaches the verifier
    assert str(other) not in call(FakeVerifier(None), **{"X-Customer-Id": str(other)}).text


def test_identity_headers_without_a_session_do_not_authenticate():
    other = str(uuid.uuid4())
    r = client_for(FakeVerifier(principal())).get(f"/who?customer_id={other}", headers={"X-Customer-Id": other, "X-Admin-Key": "k"})
    assert r.status_code == 401 and other not in r.text


def test_real_router_is_401_by_default_without_touching_the_database():
    app = FastAPI()
    app.include_router(router)
    r = TestClient(app).get("/v1/me/memory", headers={SESSION_HEADER: TOKEN})
    assert r.status_code == 401
