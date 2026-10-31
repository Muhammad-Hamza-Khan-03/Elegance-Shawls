"""The admin ingestion/review API on PostgreSQL ."""
import uuid
from datetime import datetime, timezone

import pytest

from configuration.config import settings
from repositories import staged as staged_repo
from tests.integration.api_support import ADMIN_KEY, H, ApiEnv

PRODUCT = {
    "name": "Pearl Cashmere Shawl", "slug": "pearl-cashmere-shawl",
    "cover_image_url": "https://shop.example/cdn/shop/files/a.jpg",
    "images": ["https://shop.example/cdn/shop/files/a.jpg"], "main_description": "Soft.",
    "category": "shawls", "material": "Cashmere", "sizing": None, "weight": None,
    "variants": [{"name": "Pearl", "color": "Pearl", "size": "Free Size",
                  "image_url": "https://shop.example/cdn/shop/files/a.jpg", "stock": 0}],
}


class Env(ApiEnv):
    def stage(self, slug="pearl-cashmere-shawl", pid="1001"):
        async def work(sessions):
            async with sessions() as session, session.begin():
                row, _ = await staged_repo.stage_product(
                    session, source_id="primary", source_name="Shop", source_url=f"https://shop.example/products/{slug}",
                    source_product_id=pid, source_content_hash="h", fetched_at=datetime.now(timezone.utc),
                    ingestion_job_id=None, source_price=189.0, source_currency="AUD",
                    product={**PRODUCT, "slug": slug}, source_attributes={"origin": "Nepal"},
                    missing_fields=["price", "stock"])
                return str(row.id)

        return self.run(work)

    def act(self, sid, action, **kw):
        return self.client.post(f"/products/admin/ingestion/staged/{sid}/{action}", headers=H, **kw)

    def public(self):
        return self.client.get("/products/").json()["items"]


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    return Env(migrated_url, monkeypatch)


APPROVE = {"json": {"price": 4500, "stock": 3}}


def test_every_ingestion_route_requires_admin_auth(env):
    sid = str(uuid.uuid4())
    calls = [
        ("get", "/source", {}), ("get", "/jobs", {}), ("get", f"/jobs/{sid}", {}),
        ("post", "/jobs", {"json": {"path": "/products/x"}}), ("post", f"/jobs/{sid}/cancel", {}),
        ("post", f"/jobs/{sid}/rerun", {}), ("get", "/staged", {}), ("get", f"/staged/{sid}", {}),
        ("post", f"/staged/{sid}/approve", APPROVE),
        ("post", f"/staged/{sid}/reject", {"json": {"reason": "no good"}}),
        ("post", f"/staged/{sid}/publish", {}), ("post", f"/staged/{sid}/unpublish", {}),
        ("post", f"/staged/{sid}/archive", {}),
    ]
    for method, path, kw in calls:
        url = "/products/admin/ingestion" + path
        assert getattr(env.client, method)(url, **kw).status_code == 401, url
        assert getattr(env.client, method)(url, headers={"X-Admin-Key": "wrong"}, **kw).status_code == 401, url


def test_shared_key_is_refused_when_unset_or_its_window_is_closed(env, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "")
    assert env.client.get("/products/admin/ingestion/staged", headers=H).status_code == 401
    monkeypatch.setattr(settings, "admin_api_key", H["X-Admin-Key"])
    monkeypatch.setattr(settings, "admin_legacy_key_expires_at", "")
    assert env.client.get("/products/admin/ingestion/staged", headers=H).status_code == 401


def test_staged_product_is_listed_but_never_public(env):
    sid = env.stage()
    listing = env.client.get("/products/admin/ingestion/staged?status=pending_review", headers=H).json()
    assert [i["_id"] for i in listing["items"]] == [sid]
    assert listing["items"][0]["missing_fields"] == ["price", "stock"]
    assert env.public() == []
    assert env.client.get("/products/slug/pearl-cashmere-shawl").status_code == 404


def test_staged_response_shape_keeps_the_public_contract(env):
    sid = env.stage()
    body = env.client.get(f"/products/admin/ingestion/staged/{sid}", headers=H).json()
    assert uuid.UUID(body["_id"]) == uuid.UUID(sid)                           # opaque string id under the same `_id` key
    assert {"_id", "source_id", "source_url", "status", "product", "source_attributes", "missing_fields", "stock_known",
            "product_id", "audit", "source_price", "source_currency", "created_at", "updated_at"} <= set(body)
    assert body["source_price"] == 189.0 and body["stock_known"] is False and body["product_id"] is None
    assert [(a["action"], a["actor"], a["to_status"]) for a in body["audit"]] == [("staged", "ingestion", "pending_review")]


def test_approve_creates_inactive_draft_with_reviewer_price(env):
    sid = env.stage()
    body = env.act(sid, "approve", **APPROVE).json()
    assert body["status"] == "approved" and body["product_id"] and body["missing_fields"] == []
    product = env.client.get(f"/products/admin/{body['product_id']}", headers=H).json()
    assert product["status"] == "draft" and product["is_active"] is False
    assert product["price"] == 4500 and product["currency"] == "PKR"
    assert product["variants"][0]["stock"] == 3 and product["variants"][0]["stock_status"] == "In stock"
    assert env.public() == []  # approved is still not public


def test_publish_requires_approval(env):
    sid = env.stage()
    response = env.act(sid, "publish")
    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot publish a staged product that is pending_review"
    assert env.public() == []


def test_full_lifecycle_visibility(env):
    sid = env.stage()
    approved = env.act(sid, "approve", **APPROVE).json()
    assert env.act(sid, "publish").json()["status"] == "published"
    assert [p["slug"] for p in env.public()] == ["pearl-cashmere-shawl"]
    assert env.client.get("/products/slug/pearl-cashmere-shawl").status_code == 200

    assert env.act(sid, "unpublish").json()["status"] == "unpublished"
    assert env.public() == []
    assert env.client.get("/products/slug/pearl-cashmere-shawl").status_code == 404

    assert env.act(sid, "publish").status_code == 200  # republish allowed
    assert len(env.public()) == 1
    assert env.act(sid, "archive").json()["status"] == "archived"
    assert env.public() == []
    product = env.client.get(f"/products/admin/{approved['product_id']}", headers=H).json()
    assert product["status"] == "archived" and product["is_active"] is False
    assert env.act(sid, "publish").status_code == 409  # archived is final


def test_reject_records_reason_and_stays_hidden(env):
    sid = env.stage()
    assert env.act(sid, "reject", json={"reason": "x"}).status_code == 422  # reason too short
    rejected = env.act(sid, "reject", json={"reason": "Blurry photos"}).json()
    assert rejected["status"] == "rejected" and rejected["rejection_reason"] == "Blurry photos"
    assert rejected["audit"][-1]["action"] == "reject"
    assert env.act(sid, "approve", **APPROVE).status_code == 409
    assert env.act(sid, "publish").status_code == 409
    assert env.public() == []


def test_invalid_transitions_are_rejected(env):
    sid = env.stage()
    for action in ("publish", "unpublish"):
        assert env.act(sid, action).status_code == 409
    env.act(sid, "approve", **APPROVE)
    assert env.act(sid, "approve", **APPROVE).status_code == 409  # no double approval
    assert env.act(sid, "reject", json={"reason": "too late"}).status_code == 409
    assert env.act(sid, "unpublish").status_code == 409
    assert env.sql("select count(*) from products")[0][0] == 1  # one product from the single approval


def test_unknown_and_malformed_ids(env):
    assert env.act(str(uuid.uuid4()), "approve", **APPROVE).status_code == 404
    assert env.act("nope", "publish").status_code == 400
    assert env.act("507f1f77bcf86cd799439011", "publish").status_code == 400      # a legacy ObjectId is not an identifier now
    assert env.client.get("/products/admin/ingestion/staged/nope", headers=H).status_code == 400
    assert env.client.get(f"/products/admin/ingestion/staged/{uuid.uuid4()}", headers=H).status_code == 404


def test_approve_validates_payload(env):
    sid = env.stage()
    assert env.act(sid, "approve", json={"price": -1}).status_code == 422
    assert env.act(sid, "approve", json={"stock": 1}).status_code == 422
    assert env.act(sid, "approve", json={"price": 1, "extra": 1}).status_code == 422
    assert env.client.get(f"/products/admin/ingestion/staged/{sid}", headers=H).json()["status"] == "pending_review"


def test_slug_collision_rolls_back_approval(env):
    first = env.stage("same-slug", "1")
    second = env.stage("same-slug-2", "2")
    env.act(first, "approve", **APPROVE)
    env.sql("update staged_products set product = jsonb_set(product, '{slug}', '\"same-slug\"') where id = :i", i=second)
    response = env.act(second, "approve", **APPROVE)
    assert response.status_code == 409 and response.json()["detail"] == "A product with this slug already exists"
    state = env.client.get(f"/products/admin/ingestion/staged/{second}", headers=H).json()
    assert state["status"] == "pending_review" and state["product_id"] is None
    assert [a["action"] for a in state["audit"]] == ["staged"]                 # nothing half-recorded
    assert env.sql("select count(*) from products")[0][0] == 1


def test_a_draft_the_catalogue_rejects_is_a_422_and_changes_nothing(env):
    sid = env.stage()
    env.sql("update staged_products set product = jsonb_set(product, '{name}', to_jsonb(cast(:n as text))) where id = :i",
            n="n" * 200, i=sid)                                                  # name longer than the catalogue allows
    assert env.act(sid, "approve", **APPROVE).status_code == 422
    assert env.client.get(f"/products/admin/ingestion/staged/{sid}", headers=H).json()["status"] == "pending_review"
    assert env.sql("select count(*) from products")[0][0] == 0


def test_generic_admin_routes_cannot_bypass_staged_publish(env):
    sid = env.stage()
    pid = env.act(sid, "approve", **APPROVE).json()["product_id"]
    patch = env.client.patch(f"/products/admin/{pid}/status", headers=H, json={"status": "active"})
    assert patch.status_code == 409
    product = env.client.get(f"/products/admin/{pid}", headers=H).json()
    put = env.client.put(f"/products/admin/{pid}", headers=H, json={
        "name": product["name"], "slug": product["slug"], "cover_image_url": product["cover_image_url"],
        "status": "active",
        "variants": [{"name": "v", "image_url": product["cover_image_url"], "price": 1, "stock": 1}],
    })
    assert put.status_code == 409
    assert env.public() == []
    # deactivating through the generic route remains allowed
    assert env.client.patch(f"/products/admin/{pid}/status", headers=H, json={"status": "draft"}).status_code == 200


def test_ordinary_products_are_unaffected_by_the_guard(env):
    created = env.client.post("/products/admin/", headers=H, json={
        "name": "Manual", "slug": "manual", "cover_image_url": "https://x/a.jpg",
        "variants": [{"name": "v", "image_url": "https://x/a.jpg", "price": 10, "stock": 1}],
        "status": "draft",
    }).json()
    assert env.client.patch(f"/products/admin/{created['_id']}/status", headers=H,
                            json={"status": "active"}).status_code == 200
    assert len(env.public()) == 1


def test_staged_listing_paginates_with_uuid_cursors_and_rejects_bad_ones(env):
    ids = [env.stage(f"p-{n}", str(n)) for n in range(5)]
    seen, cursor = [], None
    while True:
        url = "/products/admin/ingestion/staged?limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = env.client.get(url, headers=H).json()
        seen += [i["_id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert sorted(seen) == sorted(ids) and len(set(seen)) == 5
    for bad in ("garbage", "e30.000000000000", seen[0], "x" * 600):
        assert env.client.get(f"/products/admin/ingestion/staged?cursor={bad}", headers=H).status_code == 400, bad


# ---- job endpoints -------------------------------------------------------

def test_create_job_accepts_only_product_paths_on_configured_source(env):
    url = "/products/admin/ingestion/jobs"
    created = env.client.post(url, headers=H, json={"path": "/products/pearl"})
    assert created.status_code == 201 and created.json()["status"] == "queued"
    again = env.client.post(url, headers=H, json={"path": "/products/pearl"})
    assert again.status_code == 200 and again.json()["_id"] == created.json()["_id"]
    for bad in ("https://evil.example/products/x", "//evil.example/products/x", "/admin", "/products/../x"):
        assert env.client.post(url, headers=H, json={"path": bad}).status_code == 422, bad
    assert env.client.post(url, headers=H, json={"path": "/products/a", "url": "https://x"}).status_code == 422


def test_create_job_refused_when_source_unauthorized(env, monkeypatch):
    monkeypatch.setattr(settings, "ingestion_source_authorized", False)
    response = env.client.post("/products/admin/ingestion/jobs", headers=H, json={"path": "/products/pearl"})
    assert response.status_code == 422 and "authorized" in response.json()["detail"]


def test_cancel_and_rerun_jobs(env):
    jid = env.client.post("/products/admin/ingestion/jobs", headers=H, json={"path": "/products/pearl"}).json()["_id"]
    assert env.client.post(f"/products/admin/ingestion/jobs/{jid}/rerun", headers=H).status_code == 409
    assert env.client.post(f"/products/admin/ingestion/jobs/{jid}/cancel", headers=H).json()["status"] == "cancelled"
    assert env.client.post(f"/products/admin/ingestion/jobs/{jid}/cancel", headers=H).status_code == 409
    assert env.client.post(f"/products/admin/ingestion/jobs/{jid}/rerun", headers=H).json()["status"] == "queued"
    assert env.client.get("/products/admin/ingestion/jobs", headers=H).json()["items"][0]["_id"] == jid
    assert env.client.get(f"/products/admin/ingestion/jobs/{jid}", headers=H).json()["_id"] == jid
    assert env.client.get(f"/products/admin/ingestion/jobs/{uuid.uuid4()}", headers=H).status_code == 404
    assert env.client.get("/products/admin/ingestion/jobs/not-a-uuid", headers=H).status_code == 400


def test_database_outage_answers_503_not_500(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routes.ingestion_routes import router
    from routes.product_routes import router as products

    monkeypatch.setattr(settings, "admin_api_key", ADMIN_KEY)
    app = FastAPI()
    app.include_router(products)
    app.include_router(router)                                  # no session override and PostgreSQL not initialised
    client = TestClient(app)
    assert client.get("/products/").status_code == 503
    assert client.get("/products/admin/ingestion/staged", headers=H).status_code == 503
