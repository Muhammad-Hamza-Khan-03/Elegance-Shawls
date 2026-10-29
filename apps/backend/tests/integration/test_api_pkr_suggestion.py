"""PKR suggestion endpoint on PostgreSQL: reference-only, saves nothing, sets no price."""
import pytest

from ingestion.fx import Rate, RateUnavailable
from routes import ingestion_routes
from tests.integration.test_api_review import H, Env

STAGED_ROW = "select * from staged_products order by id"

@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    return Env(migrated_url, monkeypatch)


def stub_rate(monkeypatch, rate=Rate("aud", 200.0, "2026-10-28")):
    async def fake(currency):
        return rate
    monkeypatch.setattr(ingestion_routes, "get_pkr_rate", fake)


def test_endpoint_returns_a_reference_suggestion_and_changes_nothing(env, monkeypatch):
    stub_rate(monkeypatch)
    sid = env.stage()
    before = env.sql(STAGED_ROW)
    response = env.client.get(f"/products/admin/ingestion/staged/{sid}/pkr-suggestion", headers=H)
    assert response.status_code == 200
    body = response.json()
    assert body["source_price"] == 189.0 and body["source_currency"] == "AUD"
    assert body["suggested_pkr"] == 37800 and body["rate"] == 200.0 and body["rate_date"] == "2026-10-28"
    assert "reviewer sets the retail price" in body["note"]
    assert env.sql(STAGED_ROW) == before  # nothing saved, no price set
    assert env.sql("select count(*) from products")[0][0] == 0


def test_endpoint_requires_the_admin_key(env, monkeypatch):
    stub_rate(monkeypatch)
    sid = env.stage()
    assert env.client.get(f"/products/admin/ingestion/staged/{sid}/pkr-suggestion").status_code == 401


def test_endpoint_refuses_when_price_or_currency_is_unknown(env, monkeypatch):
    stub_rate(monkeypatch)
    for field in ("source_price", "source_currency"):
        sid = env.stage(slug=f"p-{field}", pid=field)
        env.sql(f"update staged_products set {field} = null where id = :i", i=sid)
        response = env.client.get(f"/products/admin/ingestion/staged/{sid}/pkr-suggestion", headers=H)
        assert response.status_code == 409 and "manually" in response.json()["detail"]


def test_endpoint_reports_an_unavailable_rate_and_unknown_ids(env, monkeypatch):
    async def down(currency):
        raise RateUnavailable("Exchange rate is currently unavailable")
    monkeypatch.setattr(ingestion_routes, "get_pkr_rate", down)
    sid = env.stage()
    assert env.client.get(f"/products/admin/ingestion/staged/{sid}/pkr-suggestion", headers=H).status_code == 502
    assert env.client.get("/products/admin/ingestion/staged/00000000-0000-4000-8000-000000000000/pkr-suggestion", headers=H).status_code == 404
