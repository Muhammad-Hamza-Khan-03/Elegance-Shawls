"""M1-S4: POST /v1/enquiries validates a cart against the live catalogue and issues a non-sensitive reference."""
import re
import uuid

import pytest
from alembic import command

from repositories import enquiries as repo
from tests.integration.api_support import H, ApiEnv
from tests.integration.conftest import alembic_config
from tests.integration.test_api_products import payload, variant

REF = re.compile(r"^ES-[A-HJ-NP-Z2-9]{6}$")


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    return ApiEnv(migrated_url, monkeypatch)


def make_product(env, slug="classic-pashmina", status="active", variants=None):
    body = payload(slug)
    body["status"] = status
    if variants:
        body["variants"] = variants
    created = env.client.post("/products/admin/", json=body, headers=H)
    assert created.status_code == 201, created.text
    return created.json()


def line(product, index=0, quantity=1, price=None, currency="PKR"):
    v = product["variants"][index]
    return {"product_id": product["_id"], "variant_id": v["_id"], "quantity": quantity,
            "unit_price": v["price"] if price is None else price, "currency": currency}


def post(env, *lines):
    return env.client.post("/v1/enquiries", json={"items": list(lines)})


def reasons(response):
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "cart_stale"
    return [i["reason"] for i in response.json()["detail"]["issues"]]


def count(env):
    return env.sql("select count(*) from enquiries")[0][0]


def test_multi_item_cart_gets_a_reference_and_a_server_computed_snapshot(env):
    a = make_product(env, "a", variants=[variant("Red"), variant("Blue", price=3000)])
    b = make_product(env, "b")
    response = post(env, line(a, 0, 2), line(a, 1, 1), line(b, 0, 3))
    assert response.status_code == 201, response.text
    body = response.json()
    assert REF.match(body["reference"])
    assert body["currency"] == "PKR" and body["total"] == 2 * 4500 + 3000 + 3 * 4500
    assert [(i["product"], i["color"], i["quantity"], i["unit_price"]) for i in body["items"]] == [
        ("Classic Pashmina", "Red", 2, 4500), ("Classic Pashmina", "Blue", 1, 3000), ("Classic Pashmina", "Burgundy", 3, 4500)]
    assert count(env) == 1


def test_references_are_unique_and_a_collision_is_retried(env, monkeypatch):
    product = make_product(env)
    refs = {post(env, line(product)).json()["reference"] for _ in range(8)}
    assert len(refs) == 8 and count(env) == 8

    taken = next(iter(refs))
    candidates = iter([taken, taken, "ES-ZZZZZZ"])
    monkeypatch.setattr(repo, "new_reference", lambda: next(candidates))
    assert post(env, line(product)).json()["reference"] == "ES-ZZZZZZ"


def test_only_the_minimum_is_stored(env):
    product = make_product(env)
    assert post(env, line(product)).status_code == 201
    columns = {r[0] for r in env.sql("select column_name from information_schema.columns where table_name = 'enquiries'")}
    assert columns == {"id", "reference", "items", "currency", "total", "created_at"}     # no contact details, no session id
    unknown = env.client.post("/v1/enquiries", json={"items": [line(product)], "phone": "0300"})
    assert unknown.status_code == 422                                                      # extra personal fields are refused


def test_stale_price_is_rejected_with_the_current_price_and_nothing_is_stored(env):
    product = make_product(env)
    response = post(env, line(product, price=4000))
    assert reasons(response) == ["price_changed"]
    assert response.json()["detail"]["issues"][0]["current_price"] == 4500
    assert count(env) == 0


def test_currency_mismatch_with_the_catalogue_is_stale(env):
    product = make_product(env)
    assert reasons(post(env, line(product, currency="USD"))) == ["price_changed"]


def test_stock_is_checked_per_line_and_all_problems_are_reported(env):
    product = make_product(env, variants=[variant("Red", stock=2), variant("Blue", stock=0)])
    response = post(env, line(product, 0, quantity=3), line(product, 1))
    assert reasons(response) == ["insufficient_stock", "out_of_stock"]
    assert response.json()["detail"]["issues"][0]["available"] == 2
    assert count(env) == 0
    assert post(env, line(product, 0, quantity=2)).status_code == 201                    # exactly the stock is fine


@pytest.mark.parametrize("status", ["draft", "archived", "out_of_stock"])
def test_a_product_that_is_no_longer_public_is_stale(env, status):
    product = make_product(env)
    env.client.patch(f"/products/admin/{product['_id']}/status", json={"status": status}, headers=H)
    assert reasons(post(env, line(product))) == ["unavailable"]


def test_unknown_product_unknown_variant_and_mismatched_pair_are_stale(env):
    one, two = make_product(env, "one"), make_product(env, "two")
    ghost = {**line(one), "variant_id": str(uuid.uuid4())}
    crossed = {**line(one), "product_id": two["_id"]}
    assert reasons(post(env, ghost, crossed)) == ["unavailable", "unavailable"]
    assert count(env) == 0


def test_malformed_duplicate_and_mixed_currency_carts_are_refused(env):
    product = make_product(env, variants=[variant("Red"), variant("Blue")])
    assert post(env).status_code == 422                                                   # empty
    assert post(env, line(product, quantity=0)).status_code == 422
    assert post(env, {**line(product), "variant_id": "not-a-uuid"}).status_code == 422
    assert post(env, line(product), line(product)).status_code == 422                     # same option twice
    assert post(env, line(product, 0), line(product, 1, currency="USD")).status_code == 422
    assert count(env) == 0


def test_creating_an_enquiry_changes_nothing_else(env):
    product = make_product(env)
    before = env.sql("select (select count(*) from variants where stock <> 4), (select count(*) from outbox), (select count(*) from audit_log)")
    assert post(env, line(product, quantity=4)).status_code == 201
    assert env.sql("select stock from variants") == [(4,)]                                # no reservation or decrement
    assert env.sql("select (select count(*) from variants where stock <> 4), (select count(*) from outbox), (select count(*) from audit_log)") == before
    assert not {r[0] for r in env.sql("select table_name from information_schema.tables where table_schema = 'public'")} & {"orders", "messages_outbound"}


def test_admin_lookup_requires_authentication_and_finds_by_reference(env):
    product = make_product(env, "a")
    other = make_product(env, "b")
    ref = post(env, line(product, quantity=2)).json()["reference"]
    other_ref = post(env, line(other)).json()["reference"]

    for path in ("/v1/admin/enquiries", f"/v1/admin/enquiries/{ref}"):
        assert env.client.get(path).status_code == 401
        assert env.client.get(path, headers={"X-Admin-Key": "wrong"}).status_code == 401

    detail = env.client.get(f"/v1/admin/enquiries/{ref.lower()}", headers=H)
    assert detail.status_code == 200 and detail.json()["reference"] == ref and detail.json()["items"][0]["quantity"] == 2
    assert env.client.get("/v1/admin/enquiries/ES-NOPE22", headers=H).status_code == 404

    found = env.client.get("/v1/admin/enquiries", params={"reference": other_ref}, headers=H).json()
    assert [e["reference"] for e in found] == [other_ref]
    assert env.client.get("/v1/admin/enquiries", params={"reference": "ES-NOPE22"}, headers=H).json() == []
    assert [e["reference"] for e in env.client.get("/v1/admin/enquiries", headers=H).json()] == [other_ref, ref]   # newest first


def test_migration_0008_downgrade_refuses_to_drop_references_unless_allowed(pg_url, migrated_url, pg_engine_factory, monkeypatch):
    config = alembic_config(pg_url)
    env = ApiEnv(pg_url, monkeypatch)
    env.sql("insert into enquiries (reference, items, currency, total) values ('ES-ABCDEF', '[{}]'::jsonb, 'PKR', 0)")
    try:
        monkeypatch.delenv("ALEMBIC_ALLOW_ENQUIRY_DATA_LOSS", raising=False)
        with pytest.raises(Exception, match="Refusing to downgrade 0008"):
            command.downgrade(config, "0007")
        assert count(env) == 1                                                            # untouched
        monkeypatch.setenv("ALEMBIC_ALLOW_ENQUIRY_DATA_LOSS", "1")
        command.downgrade(config, "0007")
        assert "enquiries" not in {r[0] for r in env.sql("select table_name from information_schema.tables where table_schema = 'public'")}
    finally:
        command.upgrade(config, "head")
