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


def test_every_admin_mutation_rejects_missing_and_invalid_credentials(monkeypatch):
    client, _ = make_client(monkeypatch)
    product_id = "507f1f77bcf86cd799439011"
    requests = [
        ("put", f"/products/admin/{product_id}", {"json": payload()}),
        ("patch", f"/products/admin/{product_id}/status", {"json": {"status": "draft"}}),
        ("patch", f"/products/admin/{product_id}/stock", {"json": {"variant_id": product_id, "stock": 0}}),
        ("delete", f"/products/admin/{product_id}", {}),
    ]
    for method, path, kwargs in requests:
        assert getattr(client, method)(path, **kwargs).status_code == 401
        assert getattr(client, method)(path, headers={"X-Admin-Key": "wrong"}, **kwargs).status_code == 401


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


def variant(name, **extra):
    return {
        "name": name,
        "color": name,
        "image_url": f"https://images.example.com/{name.lower()}.jpg",
        "price": 4500,
        "stock": 4,
        **extra,
    }


def test_edit_preserves_existing_variant_ids(monkeypatch):
    client, _ = make_client(monkeypatch)
    body = payload()
    body["variants"] = [variant("Burgundy"), variant("Ivory")]
    created = client.post("/products/admin/", json=body, headers=headers()).json()
    burgundy_id, ivory_id = (v["_id"] for v in created["variants"])

    edited = payload()
    edited["main_description"] = "Updated copy only"
    edited["variants"] = [
        variant("Burgundy", id=burgundy_id, image_url="https://images.example.com/new.jpg"),
        variant("Ivory", id=ivory_id),
    ]
    response = client.put(f"/products/admin/{created['_id']}", json=edited, headers=headers())
    assert response.status_code == 200
    assert [v["_id"] for v in response.json()["variants"]] == [burgundy_id, ivory_id]

    public = client.get("/products/slug/classic-pashmina").json()
    assert [v["_id"] for v in public["variants"]] == [burgundy_id, ivory_id]


def test_edit_assigns_ids_only_to_new_variants_and_drops_removed(monkeypatch):
    client, _ = make_client(monkeypatch)
    body = payload()
    body["variants"] = [variant("Burgundy"), variant("Ivory")]
    created = client.post("/products/admin/", json=body, headers=headers()).json()
    burgundy_id, ivory_id = (v["_id"] for v in created["variants"])

    edited = payload()
    edited["variants"] = [variant("Burgundy", id=burgundy_id), variant("Navy")]
    response = client.put(f"/products/admin/{created['_id']}", json=edited, headers=headers()).json()
    ids = [v["_id"] for v in response["variants"]]
    assert ids[0] == burgundy_id
    assert ids[1] not in {burgundy_id, ivory_id}

    removed = client.patch(
        f"/products/admin/{created['_id']}/stock",
        json={"variant_id": ivory_id, "stock": 3},
        headers=headers(),
    )
    assert removed.status_code == 404

    kept = client.patch(
        f"/products/admin/{created['_id']}/stock",
        json={"variant_id": burgundy_id, "stock": 0},
        headers=headers(),
    )
    assert kept.status_code == 200
    assert kept.json()["variants"][0]["stock_status"] == "Out of stock"


def test_edit_ignores_foreign_and_duplicate_variant_ids(monkeypatch):
    client, _ = make_client(monkeypatch)
    first = client.post("/products/admin/", json=payload("first-shawl"), headers=headers()).json()
    second = client.post("/products/admin/", json=payload("second-shawl"), headers=headers()).json()
    own_id = second["variants"][0]["_id"]
    foreign_id = first["variants"][0]["_id"]

    edited = payload("second-shawl")
    edited["variants"] = [
        variant("Own", id=own_id),
        variant("Duplicate", id=own_id),
        variant("Foreign", id=foreign_id),
    ]
    response = client.put(f"/products/admin/{second['_id']}", json=edited, headers=headers()).json()
    ids = [v["_id"] for v in response["variants"]]
    assert ids[0] == own_id
    assert len(set(ids)) == 3
    assert foreign_id not in ids


def test_create_ignores_submitted_variant_ids(monkeypatch):
    client, _ = make_client(monkeypatch)
    forged = "507f1f77bcf86cd799439011"
    body = payload()
    body["variants"] = [variant("Burgundy", id=forged)]
    created = client.post("/products/admin/", json=body, headers=headers()).json()
    assert created["variants"][0]["_id"] != forged


def test_stock_status_follows_stock_count(monkeypatch):
    client, _ = make_client(monkeypatch)
    body = payload()
    body["variants"] = [variant("Empty", stock=0, stock_status="In stock"), variant("Full", stock_status="Out of stock")]
    created = client.post("/products/admin/", json=body, headers=headers()).json()
    assert [v["stock_status"] for v in created["variants"]] == ["Out of stock", "In stock"]


def test_update_missing_product_returns_404(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.put(
        "/products/admin/507f1f77bcf86cd799439011", json=payload(), headers=headers()
    )
    assert response.status_code == 404
