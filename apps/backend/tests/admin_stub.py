"""Container-free admin auth: the legacy shared key (window open) with an in-memory stand-in for the audit writes."""
import uuid
from datetime import datetime, timedelta, timezone

from configuration.config import settings
from database.pg import get_pg_session

LEGACY_KEY_FUTURE = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()


class StubResult:
    def scalar_one(self):
        return uuid.uuid4()


class StubSession:
    """Accepts the audit insert/update/commit the guard performs; nothing is stored."""
    statements = 0

    async def execute(self, *args, **kwargs):
        StubSession.statements += 1
        return StubResult()

    async def commit(self): ...
    async def rollback(self): ...


def open_legacy_admin(app, monkeypatch, key: str):
    monkeypatch.setattr(settings, "admin_api_key", key)
    monkeypatch.setattr(settings, "admin_legacy_key_expires_at", LEGACY_KEY_FUTURE)

    async def stub():
        yield StubSession()

    app.dependency_overrides[get_pg_session] = stub
    return app
