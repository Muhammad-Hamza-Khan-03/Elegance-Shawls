"""Public and admin product API on PostgreSQL ."""
import uuid

import pytest

from tests.integration.api_support import H, ApiEnv

ADMIN_KEY_HEADERS = H


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


def variant(name, **extra):
    return {
        "name": name,
        "color": name,
        "image_url": f"https://images.example.com/{name.lower()}.jpg",
        "price": 4500,
        "stock": 4,
        **extra,
    }


@pytest.fixture
def client(pg_engine_factory, migrated_url, monkeypatch):
    return ApiEnv(migrated_url, monkeypatch).client


def headers():
    return H


def test_admin_routes_require_authentication(client):
    assert client.post("/products/admin/", json=payload()).status_code == 401
    assert client.get("/products/admin/").status_code == 401


def test_every_admin_mutation_rejects_missing_and_invalid_credentials(client):
    product_id = str(uuid.uuid4())
    requests = [
        ("put", f"/products/admin/{product_id}", {"json": payload()}),
        ("patch", f"/products/admin/{product_id}/status", {"json": {"status": "draft"}}),
        ("patch", f"/products/admin/{product_id}/stock", {"json": {"variant_id": product_id, "stock": 0}}),
        ("delete", f"/products/admin/{product_id}", {}),
    ]
    for method, path, kwargs in requests:
        assert getattr(client, method)(path, **kwargs).status_code == 401
        assert getattr(client, method)(path, headers={"X-Admin-Key": "wrong"}, **kwargs).status_code == 401


def test_create_duplicate_and_public_active_isolation(client):
    created = client.post("/products/admin/", json=payload(), headers=headers())
    assert created.status_code == 201
    product_id = created.json()["_id"]
    assert uuid.UUID(product_id)                                    # opaque string id under the unchanged `_id` key

    duplicate = client.post("/products/admin/", json=payload(), headers=headers())
    assert duplicate.status_code == 409 and duplicate.json()["detail"] == "Product slug already exists"

    public = client.get("/products/").json()
    assert len(public["items"]) == 1

    archived = client.delete(f"/products/admin/{product_id}", headers=headers())
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert client.get("/products/").json()["items"] == []
    assert client.get("/products/slug/classic-pashmina").status_code == 404


def test_update_status_and_variant_stock(client):
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


def test_full_update_and_validation(client):
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


def test_cursor_pagination(client):
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
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    assert {item["slug"] for item in first["items"]}.isdisjoint(
        item["slug"] for item in second["items"]
    )


def test_pagination_is_newest_first_by_created_at_then_id(client):
    for index in range(5):
        client.post("/products/admin/", json=payload(f"order-{index}"), headers=headers())
    slugs, cursor = [], None
    while True:
        page = client.get("/products/", params={"limit": 2, **({"cursor": cursor} if cursor else {})}).json()
        slugs += [i["slug"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert slugs == [f"order-{i}" for i in (4, 3, 2, 1, 0)]


@pytest.mark.parametrize("bad", ["", "garbage", "e30", "e30.deadbeef0000", "A" * 600, "a.b.c"])
def test_malformed_cursors_are_rejected_safely(client, bad):
    if bad:
        assert client.get("/products/", params={"cursor": bad}).status_code == 400
        assert client.get("/products/admin/", params={"cursor": bad}, headers=headers()).status_code == 400


def test_a_tampered_cursor_is_rejected(client):
    for index in range(3):
        client.post("/products/admin/", json=payload(f"t-{index}"), headers=headers())
    cursor = client.get("/products/?limit=1").json()["next_cursor"]
    body, _, check = cursor.partition(".")
    flipped = ("A" if body[10] != "A" else "B")
    for tampered in (body[:10] + flipped + body[11:] + "." + check, body + "." + "0" * 12, body, cursor[:-1]):
        assert client.get("/products/", params={"cursor": tampered}).status_code == 400, tampered


def test_list_response_shape_is_items_and_next_cursor(client):
    client.post("/products/admin/", json=payload(), headers=headers())
    body = client.get("/products/").json()
    assert set(body) == {"items", "next_cursor"} and body["next_cursor"] is None
    item = body["items"][0]
    assert {"_id", "name", "slug", "cover_image_url", "images", "category", "price", "currency", "status", "is_active",
            "variants", "created_at", "updated_at", "item_number"} <= set(item)
    assert {"_id", "name", "color", "size", "image_url", "price", "currency", "stock", "stock_status", "is_active"} <= set(item["variants"][0])


def test_edit_preserves_existing_variant_ids(client):
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


def test_edit_assigns_ids_only_to_new_variants_and_drops_removed(client):
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


def test_edit_ignores_foreign_and_duplicate_variant_ids(client):
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
    first_again = client.get(f"/products/admin/{first['_id']}", headers=headers()).json()
    assert [v["_id"] for v in first_again["variants"]] == [foreign_id]       # the other product is untouched


@pytest.mark.parametrize("forged", ["507f1f77bcf86cd799439011", "not-an-id", str(uuid.uuid4())])
def test_create_ignores_submitted_variant_ids(client, forged):
    body = payload()
    body["variants"] = [variant("Burgundy", id=forged)]
    created = client.post("/products/admin/", json=body, headers=headers())
    assert created.status_code == 201                                       # an unknown or legacy id is ignored, not an error
    assert created.json()["variants"][0]["_id"] != forged


def test_stock_status_follows_stock_count(client):
    body = payload()
    body["variants"] = [variant("Empty", stock=0, stock_status="In stock"), variant("Full", stock_status="Out of stock")]
    created = client.post("/products/admin/", json=body, headers=headers()).json()
    assert [v["stock_status"] for v in created["variants"]] == ["Out of stock", "In stock"]


def test_update_missing_product_returns_404(client):
    response = client.put(f"/products/admin/{uuid.uuid4()}", json=payload(), headers=headers())
    assert response.status_code == 404


def test_malformed_product_ids_are_400(client):
    for path in ("not-a-uuid", "507f1f77bcf86cd799439011"):
        assert client.get(f"/products/admin/{path}", headers=headers()).status_code == 400
        assert client.delete(f"/products/admin/{path}", headers=headers()).status_code == 400


def test_stock_endpoint_rejects_negative_and_foreign_variants(client):
    one = client.post("/products/admin/", json=payload("one"), headers=headers()).json()
    two = client.post("/products/admin/", json=payload("two"), headers=headers()).json()
    stock = lambda pid, vid, n: client.patch(f"/products/admin/{pid}/stock", json={"variant_id": vid, "stock": n}, headers=headers())
    assert stock(one["_id"], one["variants"][0]["_id"], -1).status_code == 422
    assert stock(one["_id"], two["variants"][0]["_id"], 2).status_code == 404       # another product's variant
    assert stock(str(uuid.uuid4()), one["variants"][0]["_id"], 2).status_code == 404


def test_create_with_invalid_data_is_a_422_and_saves_nothing(client):
    for bad in ({"slug": "Bad Slug"}, {"price": -1}, {"category": "hats"}, {"variants": []}):
        body = {**payload(), **bad}
        assert client.post("/products/admin/", json=body, headers=headers()).status_code == 422
    assert client.get("/products/admin/", headers=headers()).json()["items"] == []


def test_public_routes_never_show_non_active_products(client):
    for slug, status in (("live", "active"), ("hidden", "draft"), ("out", "out_of_stock"), ("old", "archived")):
        client.post("/products/admin/", json={**payload(slug), "status": status}, headers=headers())
    assert [p["slug"] for p in client.get("/products/").json()["items"]] == ["live"]
    assert [client.get(f"/products/slug/{s}").status_code for s in ("live", "hidden", "out", "old")] == [200, 404, 404, 404]
    assert len(client.get("/products/admin/", headers=headers()).json()["items"]) == 4
