"""The memory provider receives only a server-resolved customer and owns its transaction."""
import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from memory.principal import CustomerPrincipal, get_session_verifier
from memory.provider import MemoryProvider, PostgresMemoryProvider, get_memory_provider
from routes.memory_routes import router
from schemas.memory_schema import MemoryItemOut


def test_postgres_adapter_implements_the_memory_contract():
    assert isinstance(PostgresMemoryProvider(object()), MemoryProvider)


def test_provider_returns_the_public_item_shape_without_owner_or_fingerprint(monkeypatch):
    owner = uuid.uuid4()
    now = datetime.now(timezone.utc)
    item = SimpleNamespace(id=uuid.uuid4(), customer_id=owner, fingerprint="private", idempotency_key="private",
                           category="preference", key="style", value="plain", source="user_explicit", source_ref=None,
                           reason=None, version=1, retention_days=30, expires_at=now + timedelta(days=30),
                           created_at=now, updated_at=now)

    async def listed(session, customer_id, checked_at):
        assert customer_id == owner and session is sentinel
        return [item]

    from memory import service
    monkeypatch.setattr(service, "list_items", listed)
    sentinel = object()
    result = asyncio.run(PostgresMemoryProvider(sentinel).list_items(owner, now))
    assert isinstance(result[0], MemoryItemOut)
    assert "customer_id" not in result[0].model_dump() and "fingerprint" not in result[0].model_dump()


def test_provider_receives_only_the_server_verified_customer():
    owner, spoofed = uuid.uuid4(), uuid.uuid4()
    token = "cs1.contract-test"
    now = datetime.now(timezone.utc)

    class Verifier:
        async def verify(self, presented, checked_at):
            assert presented == token
            return CustomerPrincipal(owner, str(uuid.uuid4()), hashlib.sha256(token.encode()).hexdigest(), now + timedelta(hours=1))

    class Provider:
        def __init__(self):
            self.seen = []

        async def get_consent(self, customer_id):
            self.seen.append(customer_id)
            return {"granted": False, "policy_version": "test", "changed_at": None}

        async def commit(self):
            pass

        async def rollback(self):
            pass

    provider = Provider()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_verifier] = lambda: Verifier()
    app.dependency_overrides[get_memory_provider] = lambda: provider
    response = TestClient(app).get(
        f"/v1/me/memory/consent?customer_id={spoofed}",
        headers={"X-Customer-Session": token, "X-Customer-Id": str(spoofed), "X-Admin-Session": "es1.spoof"},
    )
    assert response.status_code == 200
    assert provider.seen == [owner]
    assert str(spoofed) not in response.text
