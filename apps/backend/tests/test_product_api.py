from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from configuration.config import settings
from database.db import get_db
from routes.product_routes import router


ADMIN_KEY = "test-admin-key-that-is-long-enough"


def payload(slug="classic-pashmina"):
    return {
        "name": "Classic Pashmina",
        "slug": slug,
        "cover_image_url": "https://images.example.com/cover.jpg",
        "category": "shawls",
        "item_number": f"ES-{slug}",
        "variants": [{
            "name": "Burgundy",
            "color": "Burgundy",
            "image_url": "https://images.example.com/burgundy.jpg",
            "price": 4500,
            "stock": 4,
        }],
    }


def make_client(monkeypatch):
    database = AsyncMongoMockClient().elegance_test
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: database
    monkeypatch.setattr(settings, "admin_api_key", ADMIN_KEY)
    return TestClient(app), database


def headers():
    return {"X-Admin-Key": ADMIN_KEY}


def test_admin_routes_require_authentication(monkeypatch):
    client, _ = make_client(monkeypatch)
    assert client.post("/products/admin/", json=payload()).status_code == 401
    assert client.get("/products/admin/").status_code == 401


def test_create_duplicate_and_public_active_isolation(monkeypatch):
    client, _ = make_client(monkeypatch)
    created = client.post("/products/admin/", json=payload(), headers=headers())
    assert created.status_code == 201
    product_id = created.json()["_id"]

    duplicate = client.post("/products/admin/", json=payload(), headers=headers())
    assert duplicate.status_code == 409

    public = client.get("/products/").json()
    assert len(public["items"]) == 1

    archived = client.delete(f"/products/admin/{product_id}", headers=headers())
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert client.get("/products/").json()["items"] == []
    assert client.get("/products/slug/classic-pashmina").status_code == 404


def test_update_status_and_variant_stock(monkeypatch):
    client, _ = make_client(monkeypatch)
    created = client.post("/products/admin/", json=payload(), headers=headers()).json()
    product_id = created["_id"]
    variant_id = created["variants"][0]["_id"]

    stock = client.patch(
        f"/products/admin/{product_id}/stock",
        json={"variant_id": variant_id, "stock": 0},
        headers=headers(),
    )
    assert stock.status_code == 200
    assert stock.json()["variants"][0]["stock_status"] == "Out of stock"

    draft = client.patch(
        f"/products/admin/{product_id}/status",
        json={"status": "draft"},
        headers=headers(),
    )
    assert draft.status_code == 200
    assert draft.json()["is_active"] is False
    assert client.get("/products/").json()["items"] == []


def test_full_update_and_validation(monkeypatch):
    client, _ = make_client(monkeypatch)
    created = client.post("/products/admin/", json=payload(), headers=headers()).json()
    changed = payload("updated-pashmina")
    changed["name"] = "Updated Pashmina"
    response = client.put(
        f"/products/admin/{created['_id']}", json=changed, headers=headers()
    )
    assert response.status_code == 200
    assert response.json()["slug"] == "updated-pashmina"
    assert client.get("/products/slug/updated-pashmina").status_code == 200
    assert client.get("/products/?limit=0").status_code == 422
    assert client.get("/products/?limit=101").status_code == 422
    assert client.get("/products/?cursor=not-valid").status_code == 400


def test_cursor_pagination(monkeypatch):
    client, _ = make_client(monkeypatch)
    for index in range(3):
        assert client.post(
            "/products/admin/", json=payload(f"product-{index}"), headers=headers()
        ).status_code == 201

    first = client.get("/products/?limit=2").json()
    assert len(first["items"]) == 2
    assert first["next_cursor"]
    second = client.get(
        "/products/", params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert len(second["items"]) == 1
    assert {item["slug"] for item in first["items"]}.isdisjoint(
        item["slug"] for item in second["items"]
    )
