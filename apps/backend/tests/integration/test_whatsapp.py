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


# ---- automated replies -------------------------------------------------------------------------------------------
class FakeSender:
    def __init__(self):
        self.sent = []

    async def send(self, chat, text, key):
        self.sent.append((chat, text, key))
        return f"BOT{len(self.sent)}"


def converse(env, sender, *events, now=T0 + timedelta(minutes=1)):
    from whatsapp.reply_service import maybe_reply

    async def work(sessions):
        out = []
        for e in events:
            async with sessions() as session, session.begin():
                await ingest(session, e)
            out.append(await maybe_reply(sessions, e, sender, now=now))
        return out
    return env.run(work)


def real_enquiry(env, ref="ES-ABCDEF"):
    env.sql("""insert into products(id, slug, name, cover_image_url, status, price) values ('00000000-0000-0000-0000-0000000000a1', 'wool', 'Shawl', 'https://i/x.jpg', 'active', 100)""")
    env.sql("""insert into variants(id, product_id, position, name, color, size, image_url, price, currency, stock) values
              ('00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-0000000000a1', 0, 'Red', 'Red', 'Free', 'https://i/x.jpg', 100, 'PKR', 5)""")
    items = '[{"product_id":"00000000-0000-0000-0000-0000000000a1","variant_id":"00000000-0000-0000-0000-0000000000b1","product":"Shawl","color":"Red","size":"Free","quantity":1,"unit_price":100}]'
    env.sql("insert into enquiries(reference, items, currency, total) values (:r, cast(:i as jsonb), 'PKR', 100)", r=ref, i=items)


def test_reply_flow_summary_details_then_silence_after_staff_types(env):
    real_enquiry(env)
    bot = FakeSender()
    out = converse(env, bot, event("r1", "Ref: ES-ABCDEF"), event("r2", "Name: Ayesha\nCity: Lahore\nAddress: 1 Mall Rd", minutes=1))
    assert out == ["summary", "details_done"]
    assert "1. Shawl (Red / Free) x 1 = PKR 100" in bot.sent[0][1] and bot.sent[0][2] == "reply-r1"
    assert row(env, "select customer_details ->> 'city' from enquiries")[0] == "Lahore"
    assert row(env, "select count(*) from whatsapp_messages where sent_by = 'bot'")[0] == 2
    assert row(env, "select count(*) from audit_log where action = 'whatsapp.bot_reply'")[0] == 2
    feed(env, event("s1", "I will call you", from_me=True, minutes=2))
    assert converse(env, bot, event("r3", "Ref: ES-ABCDEF again", minutes=3)) == [None]
    assert len(bot.sent) == 2


def test_stock_change_is_stated_flagged_and_not_confirmed(env):
    real_enquiry(env)
    env.sql("update variants set price = 150")
    bot = FakeSender()
    assert converse(env, bot, event("p1", "Ref: ES-ABCDEF")) == ["changed"]
    assert "PKR 150" in bot.sent[0][1]
    assert row(env, "select customer_details ->> 'staff_flag' from enquiries")[0] == "price_or_stock_changed"


def test_unlinked_chat_is_asked_for_a_reference_once_and_allowlist_silences(env, monkeypatch):
    bot = FakeSender()
    assert converse(env, bot, event("n1", "hello"), event("n2", "anyone?", minutes=1)) == ["need_reference", None]
    monkeypatch.setattr(settings, "whatsapp_reply_allowlist", "923000000000")
    other = event("n3", "hello", chat="923005555555@s.whatsapp.net")
    assert converse(env, bot, other) == [None]
    assert row(env, "select count(*) from whatsapp_messages where contact_id = (select id from whatsapp_contacts where chat_jid = '923005555555@s.whatsapp.net')")[0] == 1
    monkeypatch.setattr(settings, "whatsapp_reply_allowlist", "")


def test_bot_echo_is_not_treated_as_staff(env):
    real_enquiry(env)
    bot = FakeSender()
    converse(env, bot, event("e1", "Ref: ES-ABCDEF"))
    echo = event("BOT1", "summary text", from_me=True, minutes=1).model_copy(update={"via_bot": True})
    assert feed(env, echo) == [False]                     # already stored when the reply was sent
    echo2 = event("BOTX", "other bot text", from_me=True, minutes=2).model_copy(update={"via_bot": True})
    feed(env, echo2)
    assert row(env, "select status from enquiries")[0] == "handed_off"
    assert row(env, "select sent_by from whatsapp_messages where wa_message_id = 'BOTX'")[0] == "bot"


# ---- monitoring and retention -------------------------------------------------------------------------------------
def test_metrics_count_links_and_median_time_to_contact(env, monkeypatch):
    from whatsapp import monitoring
    monkeypatch.setattr(monitoring, "_bridge", lambda: _async(("connected", T0)))
    enquiry(env, "ES-ABCDEF")
    feed(env, event("k1", "Ref: ES-ABCDEF"), event("k2", "ok", from_me=True, minutes=30))
    env.sql("update enquiries set created_at = :t", t=T0 - timedelta(minutes=30))

    async def work(sessions):
        async with sessions() as session:
            return await monitoring.collect(session, None, now=T0 + timedelta(hours=1))
    snap = env.run(work)
    assert snap.linked_by_reference == 1 and snap.linked_by_staff == 0 and snap.median_contact_seconds == 3600
    assert snap.lag is None and snap.alerts == []


async def _async(value):
    return value


def test_retention_purges_old_messages_and_keeps_linked_chats(env):
    enquiry(env, "ES-ABCDEF")
    feed(env, event("o1", "Ref: ES-ABCDEF"), event("o2", "old chat", chat="923007777777@s.whatsapp.net"))
    env.sql("update whatsapp_messages set sent_at = now() - interval '13 months'")
    from scripts import whatsapp_retention as retention
    import argparse
    assert env.run(lambda s: _retain(retention, s)) is None
    assert row(env, "select count(*) from whatsapp_messages")[0] == 0
    assert row(env, "select count(*) from whatsapp_contacts")[0] == 1         # the chat with an enquiry stays; the empty unlinked one goes


async def _retain(retention, sessions):
    from sqlalchemy import text
    async with sessions() as session, session.begin():
        for statement in retention.PURGE:
            await session.execute(text(statement), {"months": 12})


# ---- catalogue assistant, voice, status messages ------------------------------------------------------------------
def seed_catalogue(env):
    real_enquiry(env, "ES-ZZZZZ2")


class ScriptedGateway:
    """Stands in for the LLM gateway: returns the scripted texts in call order and records what the model was shown."""

    def __init__(self, *texts):
        self.texts, self.prompts = list(texts), []

    async def complete(self, messages, logical="default", personal=False):
        from types import SimpleNamespace
        self.prompts.append("\n".join(m["content"] for m in messages))
        if not self.texts:
            raise RuntimeError("model unavailable")
        return SimpleNamespace(text=self.texts.pop(0))


def use_model(monkeypatch, *texts):
    import whatsapp.assistant as assistant
    gateway = ScriptedGateway(*texts)
    monkeypatch.setattr(settings, "whatsapp_assistant_enabled", True)
    monkeypatch.setattr(settings, "whatsapp_site_url", "https://shop.example")
    monkeypatch.setattr(assistant, "get_gateway", lambda: gateway)
    monkeypatch.setattr(assistant, "_digest_cache", None)
    return gateway


def test_model_understands_the_message_and_the_reply_is_grounded_in_the_catalogue(env, monkeypatch):
    seed_catalogue(env)
    gateway = use_model(monkeypatch, '{"action": "search", "search": {"q": "shawl", "colour": "red", "max_price": 5000}}',
                        "Mil gaya! Neeche red shawl hai, link kholein aur Order on WhatsApp dabayein.")
    bot = FakeSender()
    assert converse(env, bot, event("a1", "red shawl 5k se kam dikhao")) == ["assistant"]
    reply = bot.sent[0][1]
    assert reply.startswith("Mil gaya!") and "Shawl (Red): PKR 100" in reply and "https://shop.example/product/wool" in reply
    assert "red 1" in gateway.prompts[0] and "PKR 100 to 100" in gateway.prompts[0]      # the stock summary is read live from the database
    assert "at most PKR 5000" in gateway.prompts[1] and "Shawl (shawl)" not in gateway.prompts[1]


def test_customer_can_order_and_leave_delivery_details_entirely_in_chat(env, monkeypatch):
    seed_catalogue(env)
    order = '{"action": "order", "order": {"lines": [{"q": "shawl", "colour": "red", "quantity": 2}], "confirmed": %s}}'
    gateway = use_model(monkeypatch, order % "false", "Here is your order, reply yes to place it.",
                        order % "true", "Placed! Please send your name, city and address.",
                        '{"action": "details", "details": {"name": "Ayesha", "city": "Lahore", "address": null}}', "Thanks Ayesha, one last thing: your address.")
    bot = FakeSender()
    assert converse(env, bot, event("o1", "2 red shawls please")) == ["assistant"]
    assert "• 2 x Shawl (Red): PKR 100" in bot.sent[0][1] and "Total: PKR 200" in bot.sent[0][1]
    assert row(env, "select count(*) from enquiries")[0] == 1                               # a summary alone creates nothing
    assert converse(env, bot, event("o2", "yes", minutes=1)) == ["assistant"]
    reference, total, linked = row(env, "select reference, total, whatsapp_contact_id is not null from enquiries where reference <> 'ES-ZZZZZ2'")
    assert total == 200 and linked
    assert "Order enquiry placed: reference " + reference in gateway.prompts[3] and "not confirmed" in gateway.prompts[3]
    assert converse(env, bot, event("o3", "I am Ayesha from Lahore", minutes=2)) == ["assistant"]
    assert row(env, f"select customer_details->>'name', customer_details->>'city' from enquiries where reference = '{reference}'") == ("Ayesha", "Lahore")
    assert "address" in gateway.prompts[5]                                                    # the model is told exactly what is still missing


def test_an_unconfirmed_yes_with_no_summary_shown_creates_nothing(env, monkeypatch):
    seed_catalogue(env)
    use_model(monkeypatch, '{"action": "order", "order": {"lines": [{"q": "shawl", "quantity": 1}], "confirmed": true}}', "Reply yes to place it.")
    assert converse(env, FakeSender(), event("o4", "order it")) == ["assistant"]
    assert row(env, "select count(*) from enquiries")[0] == 1


def test_a_colour_the_shop_does_not_stock_is_never_searched_and_the_model_is_told(env, monkeypatch):
    seed_catalogue(env)
    gateway = use_model(monkeypatch, '{"action": "search", "search": {"q": "shawl", "colour": "purple"}}', "We do not have purple right now, but we have red.")
    bot = FakeSender()
    assert converse(env, bot, event("a3", "purple shawl")) == ["assistant"]
    assert "not in stock" in gateway.prompts[1] and "Shawl (Red)" not in bot.sent[0][1]


def test_model_can_answer_directly_but_cannot_invent_links_and_failures_fall_back_to_a_person(env, monkeypatch):
    seed_catalogue(env)
    use_model(monkeypatch, '{"action": "reply", "reply": "Assalam o Alaikum! How can I help you today?"}')
    bot = FakeSender()
    assert converse(env, bot, event("a4", "hi")) == ["assistant"] and bot.sent[0][1].startswith("Assalam o Alaikum!")
    use_model(monkeypatch, '{"action": "reply", "reply": "Pay here https://evil.example/pay"}')
    assert converse(env, bot, event("a5", "hello", chat="923000000005@s.whatsapp.net")) == ["holding"]      # an unknown link is rejected
    use_model(monkeypatch, '{"action": "handoff"}')
    assert converse(env, bot, event("a6", "where is my parcel", chat="923000000006@s.whatsapp.net")) == ["holding"]
    use_model(monkeypatch)                                                                                         # the model is down
    assert converse(env, bot, event("a7", "red shawl", chat="923000000007@s.whatsapp.net")) == ["holding"]


def test_assistant_falls_back_to_the_holding_reply_when_it_has_nothing(env, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_assistant_enabled", True)
    bot = FakeSender()
    assert converse(env, bot, event("a2", "remember I like brown")) == ["holding"]      # no model configured: a person follows up
    assert "team member" in bot.sent[0][1]


def test_status_message_sends_inside_an_open_chat_and_marks_contacted(env, monkeypatch):
    real_enquiry(env)
    settings.whatsapp_bridge_enabled = True
    sent = []

    async def fake_send(self, chat, text, key):
        sent.append((chat, text, key))
        return "STATUS1"
    monkeypatch.setattr("whatsapp.reply_service.BridgeSender.send", fake_send)
    try:
        feed(env, event("s0", "Ref: ES-ABCDEF"))
        ok = env.client.post("/v1/admin/enquiries/ES-ABCDEF/whatsapp/message", json={"template": "confirmed", "idempotency_key": "click-0001"}, headers=H)
        assert ok.status_code == 200 and "confirmed by our team" in sent[0][1] and sent[0][0] == CHAT
        assert row(env, "select status from enquiries")[0] == "contacted"
        assert row(env, "select sent_by from whatsapp_messages where wa_message_id = 'STATUS1'")[0] == "staff"
        assert env.client.post("/v1/admin/enquiries/ES-ABCDEF/whatsapp/message", json={"template": "refunded", "idempotency_key": "click-0002"}, headers=H).status_code == 422
        assert env.client.post("/v1/admin/enquiries/ES-NOPE22/whatsapp/message", json={"template": "dispatched", "idempotency_key": "click-0003"}, headers=H).status_code == 404
    finally:
        settings.whatsapp_bridge_enabled = False
