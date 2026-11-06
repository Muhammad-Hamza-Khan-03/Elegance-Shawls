"""WhatsApp bridge backend against real PostgreSQL: idempotent ingestion, reference linking, contacted, admin API, off switch."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from configuration.config import settings
from repositories import enquiries as enquiry_repo  # noqa: F401  (ensures the model graph is imported)
from routes.whatsapp_routes import admin_router, public_router
from tests.integration.api_support import H, ApiEnv
from whatsapp.consumer import STREAM, handle_entry
from whatsapp.ingest import ingest
from whatsapp.matching import InboundEvent

T0 = datetime(2026, 11, 6, 14, 0, tzinfo=timezone.utc)
CHAT = "923001234567@s.whatsapp.net"
ITEMS = '[{"product_id":"p","variant_id":"v","product":"Shawl","color":"Red","size":"Free","quantity":1,"unit_price":100}]'


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    e = ApiEnv(migrated_url, monkeypatch)
    e.app.include_router(public_router)
    e.app.include_router(admin_router)
    yield e
    # The database is shared: leave no chat rows behind (they would block the reversibility test's downgrade).
    e.sql("delete from whatsapp_messages")
    e.sql("delete from enquiries")
    e.sql("delete from whatsapp_contacts")


def enquiry(env, ref):
    env.sql("insert into enquiries(reference, items, currency, total) values (:r, cast(:i as jsonb), 'PKR', 100)", r=ref, i=ITEMS)


def event(wa_id, text, *, from_me=False, chat=CHAT, minutes=0):
    return InboundEvent(v=1, wa_id=wa_id, chat=chat, from_me=from_me, type="text", text=text, ts=T0 + timedelta(minutes=minutes))


def feed(env, *events):
    async def work(sessions):
        out = []
        for e in events:
            async with sessions() as session, session.begin():
                out.append(await ingest(session, e))
        return out
    return env.run(work)


def row(env, sql):
    return env.sql(sql)[0]


def test_reference_links_stores_once_and_staff_reply_marks_contacted(env):
    enquiry(env, "ES-ABCDEF")
    first = event("m1", "Order please Ref: es-abcdef")
    assert feed(env, first, first) == [True, False]                      # redelivery stores nothing
    assert row(env, "select count(*) from whatsapp_messages")[0] == 1
    assert row(env, "select link_source, status from enquiries")[:] == ("reference", "handed_off")

    assert feed(env, event("m2", "Hello, which colour?")) == [True]     # follow-up attaches to the open enquiry
    assert row(env, "select count(*) from whatsapp_messages where enquiry_id is not null")[0] == 2

    feed(env, event("m3", "Confirming stock", from_me=True, minutes=5), event("m4", "second staff msg", from_me=True, minutes=6))
    assert row(env, "select status, bot_paused_until is not null from enquiries") == ("contacted", True)
    assert row(env, "select count(*) from audit_log where actor_id = 'system:whatsapp'")[0] == 1


def test_unknown_reference_or_none_stays_unlinked_and_listed(env):
    feed(env, event("u1", "Ref: ES-ZZZZZZ"), event("u2", "hi", chat="923009999999@s.whatsapp.net"))
    assert row(env, "select count(*) from enquiries where whatsapp_contact_id is not null")[0] == 0
    body = env.client.get("/v1/admin/whatsapp/unlinked", headers=H)
    assert body.status_code == 503                                         # switch still off
    settings.whatsapp_bridge_enabled = True
    try:
        body = env.client.get("/v1/admin/whatsapp/unlinked", headers=H).json()
        assert len(body["items"]) == 2 and body["next_cursor"] is None
        contact = body["items"][0]["id"]
        enquiry(env, "ES-GHJKMN")
        ok = env.client.post("/v1/admin/whatsapp/link", json={"contact_id": contact, "enquiry_reference": "es-ghjkmn"}, headers=H)
        assert ok.status_code == 200 and ok.json()["link_source"] == "staff"
        assert len(env.client.get("/v1/admin/whatsapp/unlinked", headers=H).json()["items"]) == 1
        timeline = env.client.get("/v1/admin/enquiries/ES-GHJKMN/whatsapp", headers=H).json()
        assert timeline["items"] and timeline["status"] == "handed_off"
        missing = env.client.post("/v1/admin/whatsapp/link", json={"contact_id": contact, "enquiry_reference": "ES-NOPE22"}, headers=H)
        assert missing.status_code in (404, 409)
    finally:
        settings.whatsapp_bridge_enabled = False


def test_reference_cannot_steal_an_enquiry_linked_to_another_chat(env):
    enquiry(env, "ES-ABCDEF")
    feed(env, event("a1", "Ref: ES-ABCDEF"), event("b1", "Ref: ES-ABCDEF", chat="923008888888@s.whatsapp.net"))
    assert row(env, "select count(distinct whatsapp_contact_id) from enquiries")[0] == 1
    assert row(env, "select count(*) from whatsapp_messages where enquiry_id is not null")[0] == 1


def test_off_switch_gates_admin_routes_but_mode_is_public(env):
    assert env.client.get("/v1/whatsapp/mode").json() == {"mode": "link"}
    for path in ("/v1/admin/whatsapp/status", "/v1/admin/whatsapp/unlinked"):
        r = env.client.get(path, headers=H)
        assert r.status_code == 503 and r.json()["detail"] == {"code": "whatsapp_disabled"}


class FakeRedis:
    def __init__(self):
        self.acked, self.dead = [], []

    async def xack(self, *a):
        self.acked.append(a[-1])

    async def xadd(self, stream, fields):
        self.dead.append(stream)


def test_consumer_acks_after_commit_and_dead_letters_poison_entries(env):
    redis, attempts = FakeRedis(), {}

    async def work(sessions):
        good = event("c1", "hello").model_dump_json()
        await handle_entry(sessions, redis, "1-0", {b"event": good.encode()}, attempts)
        await handle_entry(sessions, redis, "2-0", {b"event": b'{"v": 2}'}, attempts)      # malformed: dead at once
    env.run(work)
    assert redis.acked == ["1-0", "2-0"] and redis.dead == ["wa:dead"]
    assert row(env, "select count(*) from whatsapp_messages")[0] == 1
