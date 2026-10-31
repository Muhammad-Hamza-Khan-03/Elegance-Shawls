"""M3-S3: POST /v1/assistant/actions/execute against the real catalogue. Disposable data; no message is ever sent."""
import logging
import re
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.integration.api_support import ApiEnv
from tests.integration.test_api_enquiries import make_product

URL = "/v1/assistant/actions/execute"
ENV: list = []  # the live ApiEnv, so item() can read the current revision
REF = re.compile(r"^ES-[A-HJ-NP-Z2-9]{6}$")


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    e = ApiEnv(migrated_url, monkeypatch)
    ENV[:] = [e]
    return e


def item(product, quantity=1, **over):
    v = product["variants"][0]
    revision = ENV[0].sql(f"select revision from products where id = '{product['_id']}'")[0][0]
    base = {"product_id": product["_id"], "variant_id": v["_id"], "quantity": quantity, "expected_revision": revision,
            "expected_unit_price": v["price"], "currency": "PKR"}
    return {**base, **over}


def body(action, params, key="idem_0123456789abcdef", **over):
    return {"session_id": "sess_1", "idempotency_key": key, "action_type": action, "confirmed": True, "params": params, **over}


def enquiries(env):
    return env.sql("select count(*) from enquiries")[0][0]


def test_enquiry_executes_once_and_replay_returns_same_reference(env, caplog):
    p = make_product(env)
    req = body("start_whatsapp_enquiry", {"items": [item(p, 2)]})
    with caplog.at_level(logging.INFO, logger="elegance.actions"):
        first = env.client.post(URL, json=req)
        again = env.client.post(URL, json=req)
    assert first.status_code == 200, first.text
    r = first.json()
    assert r["status"] == "executed" and r["replayed"] is False and REF.match(r["result"]["reference"])
    assert r["result"]["items"] == [{"product_id": p["_id"], "variant_id": p["variants"][0]["_id"], "quantity": 2, "slug": p["slug"]}]
    assert again.json()["replayed"] is True and again.json()["result"] == r["result"]
    assert enquiries(env) == 1
    assert "sess_1" not in caplog.text and "expected_unit_price" not in caplog.text


def test_add_to_cart_is_revalidated_and_creates_no_enquiry(env):
    p = make_product(env)
    ok = env.client.post(URL, json=body("add_to_cart", item(p, 3)))
    assert ok.status_code == 200 and ok.json()["result"]["items"][0]["quantity"] == 3 and "reference" not in ok.json()["result"]
    assert enquiries(env) == 0


@pytest.mark.parametrize("over, reason", [
    ({"expected_unit_price": 1}, "stale_price"), ({"expected_revision": 99}, "stale_revision"),
    ({"quantity": 500}, "insufficient_stock"), ({"product_id": "11111111-1111-4111-8111-111111111111"}, "product_not_found"),
])
def test_stale_or_unknown_state_is_409_and_nothing_is_created(env, over, reason):
    p = make_product(env)
    r = env.client.post(URL, json=body("start_whatsapp_enquiry", {"items": [item(p, **over)]}))
    assert r.status_code == 409 and r.json()["detail"] == {"status": "rejected", "reason": reason}
    assert enquiries(env) == 0


def test_stock_change_after_proposal_is_caught_at_execution(env):
    p = make_product(env)
    env.sql(f"update variants set stock = 0 where id = '{p['variants'][0]['_id']}'")
    r = env.client.post(URL, json=body("add_to_cart", item(p)))
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "out_of_stock"


def test_draft_product_is_not_executable(env):
    p = make_product(env, "hidden", status="draft")
    assert env.client.post(URL, json=body("add_to_cart", item(p))).json()["detail"]["reason"] == "product_unavailable"


def test_same_key_different_params_conflicts(env):
    p = make_product(env)
    env.client.post(URL, json=body("start_whatsapp_enquiry", {"items": [item(p, 1)]}))
    r = env.client.post(URL, json=body("start_whatsapp_enquiry", {"items": [item(p, 2)]}))
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "idempotency_conflict" and enquiries(env) == 1


@pytest.mark.parametrize("bad", [{"confirmed": False}, {"confirmed": "yes"}, {"action_type": "show_product"}, {"action_type": "place_order"}, {"session_id": "has space"}])
def test_unconfirmed_or_unknown_requests_are_422_and_do_nothing(env, bad):
    p = make_product(env)
    assert env.client.post(URL, json={**body("add_to_cart", item(p)), **bad}).status_code == 422
    assert enquiries(env) == 0


def test_replay_and_conflict_are_durable_across_independent_workers(env, migrated_url, monkeypatch):
    p = make_product(env)
    req = body("start_whatsapp_enquiry", {"items": [item(p, 2)]})
    first = env.client.post(URL, json=req).json()
    other = ApiEnv(migrated_url, monkeypatch)             # a second app instance: no shared process memory, same database
    again = other.client.post(URL, json=req)
    clash = other.client.post(URL, json=body("start_whatsapp_enquiry", {"items": [item(p, 3)]}))
    assert again.json()["replayed"] is True and again.json()["result"] == first["result"] and enquiries(env) == 1
    assert clash.status_code == 409 and clash.json()["detail"]["reason"] == "idempotency_conflict"
    row = env.sql("select status, attempt, audit->>'enquiry_reference', replay_count from action_executions")
    assert row == [("committed", 1, first["result"]["reference"], 1)]


def test_simultaneous_requests_from_two_workers_create_one_enquiry(env, migrated_url, monkeypatch):
    p = make_product(env)
    req = body("start_whatsapp_enquiry", {"items": [item(p, 2)]})
    clients = [env.client, ApiEnv(migrated_url, monkeypatch).client]
    with ThreadPoolExecutor(8) as pool:
        replies = list(pool.map(lambda n: clients[n % 2].post(URL, json=req), range(8)))
    ok = [r.json() for r in replies if r.status_code == 200]
    assert ok and {r["result"]["reference"] for r in ok} == {ok[0]["result"]["reference"]} and sum(not r["replayed"] for r in ok) == 1
    assert all(r.json()["detail"]["reason"] == "execution_in_progress" for r in replies if r.status_code == 409)
    assert enquiries(env) == 1
    assert env.client.post(URL, json=req).json()["result"] == ok[0]["result"]


def test_stale_state_after_a_committed_execution_still_replays_and_records_nothing_new(env):
    p = make_product(env)
    req = body("add_to_cart", item(p, 2))
    first = env.client.post(URL, json=req).json()
    env.sql(f"update variants set stock = 0 where id = '{p['variants'][0]['_id']}'")
    again = env.client.post(URL, json=req)
    assert again.status_code == 200 and again.json()["replayed"] is True and again.json()["result"] == first["result"]
    assert env.sql("select count(*) from action_executions") == [(1,)]
