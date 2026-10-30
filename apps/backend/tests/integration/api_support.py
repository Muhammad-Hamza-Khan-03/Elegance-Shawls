"""FastAPI app wired to the real migrated PostgreSQL for route tests (sync TestClient, one session per request)."""
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from configuration.config import settings
from database.pg import get_pg_session, make_engine
from routes.admin_routes import accounts_router, audit_router, auth_router
from routes.action_routes import router as action_router
from routes.enquiry_routes import admin_router as enquiry_admin_router, router as enquiry_router
from routes.ingestion_routes import router as ingestion_router
from routes.job_routes import router as job_router
from routes.llm_routes import admin_router as llm_admin_router, router as llm_router
from routes.product_routes import router as product_router, search_router

ADMIN_KEY = "test-admin-key-that-is-long-enough"
H = {"X-Admin-Key": ADMIN_KEY}


class ApiEnv:
    def __init__(self, url: str, monkeypatch):
        self.url = url
        app = FastAPI()
        app.include_router(product_router)
        app.include_router(search_router)
        app.include_router(ingestion_router)
        for router in (auth_router, accounts_router, audit_router, job_router, llm_router, llm_admin_router, enquiry_router, enquiry_admin_router, action_router):
            app.include_router(router)

        async def session_per_request():
            engine = make_engine(url)                      # each TestClient request runs in its own event loop
            try:
                async with AsyncSession(engine, expire_on_commit=False) as session:
                    yield session
            finally:
                await engine.dispose()

        app.dependency_overrides[get_pg_session] = session_per_request
        # The pre-existing suites authenticate with the shared key; account tests close this window themselves.
        monkeypatch.setattr(settings, "admin_api_key", ADMIN_KEY)
        monkeypatch.setattr(settings, "admin_legacy_key_expires_at", (datetime.now(timezone.utc) + timedelta(days=30)).isoformat())
        monkeypatch.setattr(settings, "ingestion_source_domain", "shop.example")
        monkeypatch.setattr(settings, "ingestion_source_authorized", True)
        self.app, self.client = app, TestClient(app)

    def run(self, work):
        """Run `async def work(sessions)` outside the HTTP layer (seeding and direct assertions)."""
        async def go():
            engine = make_engine(self.url)
            try:
                return await work(async_sessionmaker(engine, expire_on_commit=False))
            finally:
                await engine.dispose()

        return asyncio.run(go())

    def sql(self, statement: str, **params):
        async def work(sessions):
            async with sessions() as session, session.begin():
                result = await session.execute(text(statement), params)
                return result.all() if result.returns_rows else None

        return self.run(work)
