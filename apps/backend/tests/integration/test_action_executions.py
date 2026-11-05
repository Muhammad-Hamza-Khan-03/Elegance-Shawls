"""M3-S3 on real PostgreSQL (skipped without Docker): atomic claim, durable replay, conflict, live-catalogue check."""
import asyncio
import time

import pytest

from actions import execution as x
from actions import kernel as k
from routes.action_routes import router
from tests.integration.api_support import H, ApiEnv
from tests.integration.test_api_products import payload, variant

AID, SID = "act_0123456789abcdef0123", "sess-1"


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    monkeypatch.setenv("ASSISTANT_ACTIONS_ENABLED", "true")
    env = ApiEnv(migrated_url, monkeypatch)
    env.app.include_router(router)
    return env


def body(env, quantity=1, status="active"):
    created = env.client.post("/products/admin/", json={**payload("exec-shawl"), "status": status, "variants": [variant("Brown")]}, headers=H).json()
    line = {"product_id": created["_id"], "variant_id": created["variants"][0]["_id"], "quantity": quantity}
    fp = k._fingerprint("add_to_cart", SID, line)
    now = time.time()
    return {"action_id": AID, "name": "add_to_cart", "session_id": SID, "params": line,
            "confirmation": {"action_id": AID, "session_id": SID, "fingerprint": fp, "confirmed_at": now - 1, "expires_at": now + 60, "explicit": True}}


def test_execute_replays_durably_and_rejects_conflicts(env):
    b = body(env)
    first = env.client.post("/v1/assistant/actions/execute", json=b).json()
    assert first["status"] == "executed" and first["replayed"] is False and first["intent"]["items"] == [b["params"]]
    again = env.client.post("/v1/assistant/actions/execute", json=b).json()
    assert again["replayed"] is True and again["intent"] == first["intent"]
    assert env.sql("SELECT count(*) FROM action_executions")[0][0] == 1
    changed = {**b, "params": {**b["params"], "quantity": 2}}
    changed["confirmation"] = {**b["confirmation"], "fingerprint": k._fingerprint("add_to_cart", SID, changed["params"])}
    res = env.client.post("/v1/assistant/actions/execute", json=changed)
    assert res.status_code == 409 and res.json()["reason"] == "idempotency_conflict"


def test_draft_product_is_rejected(env):
    res = env.client.post("/v1/assistant/actions/execute", json=body(env, status="draft"))
    assert res.status_code == 422 and res.json()["reason"] == "unavailable_item"
    assert env.sql("SELECT count(*) FROM action_executions")[0][0] == 0


def test_pg_store_claims_once_in_parallel(env):
    async def work(sessions):
        async def claim():
            async with sessions() as s, s.begin():
                return await x.PgStore(s).claim(SID, AID, "a" * 64, "add_to_cart", {"intent": {}})
        return await asyncio.gather(*(claim() for _ in range(6)))
    assert sorted(c for _, _, c in env.run(work)) == [False] * 5 + [True]
