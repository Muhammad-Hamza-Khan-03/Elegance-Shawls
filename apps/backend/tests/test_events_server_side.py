import asyncio

import pytest
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

import main
from configuration.config import settings
from database.pg import get_pg_session
from events import recorder
from events.session import mint_session_token, verify_session_token
from models.relational_model import Product, Variant
from repositories import products as product_repo
from routes.product_routes import router as product_router
from tests.test_events_api import KEY, FakeSession
from workers import jobs
from workers.settings import WorkerSettings


class Opened(FakeSession):
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def transient_product(slug):
    """An in-memory catalogue row (never persisted), enough for the public listing's response model."""
    now = datetime.now(timezone.utc)
    product = Product(
        id=uuid.uuid4(), slug=slug, name=slug.title(), category="shawls", status="active", is_active=True,
        cover_image_url="https://img.example/c.jpg", images=["https://img.example/c.jpg"], price=100, currency="PKR",
        revision=1, created_at=now, updated_at=now)
    product.variants = [Variant(id=uuid.uuid4(), product_id=product.id, position=0, name="V", size="Free Size",
                                image_url="https://img.example/v.jpg", price=100, currency="PKR", stock=2,
                                stock_status="In stock", is_active=True)]
    return product


@pytest.fixture
def listing(monkeypatch):
    """The real listing route with a stubbed repository read, so event recording is tested without a database."""
    monkeypatch.setattr(settings, "session_signing_key", KEY)
    products = [transient_product("a-shawl"), transient_product("b-shawl")]

    async def list_products(session, *, public, limit, after=None, q=None):
        assert public is True
        return product_repo.Page(products, None)

    monkeypatch.setattr(product_repo, "list_products", list_products)
    app = FastAPI()
    app.include_router(product_router)

    async def no_session():
        yield None

    app.dependency_overrides[get_pg_session] = no_session
    fake = Opened()
    monkeypatch.setattr(recorder, "open_session", lambda: fake)
    client = TestClient(app)
    client.fake = fake
    return client


def test_listing_records_an_impression_with_positions_and_parsed_params(listing):
    response = listing.get("/products/?limit=5")
    assert response.status_code == 200
    [row] = listing.fake.rows
    assert row.type == "impression" and row.session_id == "unattributed"
    assert row.payload["surface"] == "listing" and row.payload["limit"] == 5 and row.payload["paged"] is False
    assert row.payload["returned"] == 2 and row.payload["product_ids"].split(",") == [i["_id"] for i in response.json()["items"]]


def test_listing_uses_a_valid_anonymous_session_only(listing):
    token = mint_session_token()
    listing.get("/products/", headers={"X-Session-Token": token})
    tampered = token[:-1] + ("1" if token[-1] == "0" else "0")                # always differs from the real signature
    listing.get("/products/", headers={"X-Session-Token": tampered})           # tampered: not attributed
    assert [r.session_id for r in listing.fake.rows] == [verify_session_token(token), "unattributed"]


@pytest.mark.parametrize("header", [{"DNT": "1"}, {"Sec-GPC": "1"}])
def test_listing_respects_do_not_track_and_gpc(listing, header):
    assert listing.get("/products/", headers=header).status_code == 200
    assert listing.fake.rows == []


def test_listing_records_nothing_without_a_signing_key(listing, monkeypatch):
    monkeypatch.setattr(settings, "session_signing_key", "")
    assert listing.get("/products/").status_code == 200
    assert listing.fake.rows == []


def test_listing_still_succeeds_when_recording_fails(listing, monkeypatch):
    class Broken(Opened):
        async def commit(self):
            raise ConnectionError("postgres down")

    monkeypatch.setattr(recorder, "open_session", lambda: Broken())
    response = listing.get("/products/")
    assert response.status_code == 200 and len(response.json()["items"]) == 2


def test_listing_still_succeeds_when_postgres_is_not_initialised(listing, monkeypatch):
    monkeypatch.setattr(recorder, "open_session", lambda: None)
    assert listing.get("/products/").status_code == 200


def test_event_batches_from_do_not_track_browsers_are_accepted_but_not_stored(monkeypatch):
    from database.pg import get_pg_session

    monkeypatch.setattr(settings, "session_signing_key", KEY)
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 1000)
    monkeypatch.setattr(settings, "events_rate_limit_per_minute", 1000)
    fake, app = FakeSession(), main.create_app()

    async def override():
        yield fake

    app.dependency_overrides[get_pg_session] = override
    response = TestClient(app).post("/v1/events", json={"events": [{"type": "view"}]}, headers={"DNT": "1"})
    assert response.status_code == 202 and response.json() == {"accepted": 0}
    assert fake.rows == [] and "set-cookie" not in response.headers


def test_retention_is_scheduled_on_the_arq_worker_cron():
    [job] = [c for c in WorkerSettings.cron_jobs if c.coroutine is jobs.purge_events_job]
    assert (job.hour, job.minute) == (3, 17) and job.unique is True
    assert jobs.purge_events_job in WorkerSettings.functions


def test_retention_job_purges_through_the_worker_session(monkeypatch):
    from events import retention

    called = {}

    async def fake_purge(session):
        called["session"] = session
        return 7

    class Sessions:
        def __call__(self):
            return Opened()

    monkeypatch.setattr(retention, "purge_expired_events", fake_purge)
    assert asyncio.run(jobs.purge_events_job({"pg_sessions": Sessions()})) == {"deleted": 7}
    assert isinstance(called["session"], Opened)


def test_retention_job_is_a_noop_without_postgres():
    assert asyncio.run(jobs.purge_events_job({})) == {"skipped": "postgres is not configured"}
