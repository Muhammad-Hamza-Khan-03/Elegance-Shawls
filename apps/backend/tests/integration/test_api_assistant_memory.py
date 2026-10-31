"""Saved memory in the assistant: consent-first, deterministic re-ordering, explicit remember-then-confirm, and the LLM privacy gate."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from assistant.grounded import catalogue_session, optional_principal
from configuration.config import settings
from database.pg import get_pg_session
from memory import service
from memory.principal import CustomerPrincipal
from repositories import customer_auth as customers
from routes.assistant_routes import router as assistant_router
from schemas.memory_schema import MemoryCreate
from tests.integration.api_support import H, ApiEnv
from tests.integration.test_api_products import payload, variant

KEY = "idem_" + "a" * 24
NOW = datetime.now(timezone.utc)


class StubGateway:
    def __init__(self, models=(), text="Ok."):
        self.models, self.text, self.prompts, self.calls = list(models), text, [], []

    def chain(self, *_, **__):
        if not self.models:
            raise RuntimeError("no personal chain")
        return self.models

    async def complete(self, messages, **kwargs):
        self.prompts.append(messages[1]["content"])
        self.calls.append(kwargs)
        return type("R", (), {"text": self.text})()


@pytest.fixture
def world(pg_engine_factory, migrated_url, monkeypatch):
    env = ApiEnv(migrated_url, monkeypatch)
    monkeypatch.setattr(settings, "assistant_catalogue", True)
    env.app.include_router(assistant_router)
    env.app.dependency_overrides[catalogue_session] = env.app.dependency_overrides[get_pg_session]
    for slug, name, colour, price in [("red-1", "Ruby Shawl", "Red", 3000), ("brown-1", "Cocoa Shawl", "Brown", 3500), ("brown-2", "Walnut Shawl", "Brown", 9000)]:
        body = {**payload(slug), "name": name, "status": "active", "variants": [variant(name, color=colour, price=price, stock=3)]}
        assert env.client.post("/products/admin/", json=body, headers=H).status_code == 201

    async def make(sessions):
        async with sessions() as s:
            cid = await customers.customer_for_identity(s, "google", "sub-" + uuid.uuid4().hex[:8])
            await s.commit()
            return cid
    env.customer = env.run(make)
    env.principal = CustomerPrincipal(env.customer, "s1", "x" * 64, NOW + timedelta(hours=1))
    env.app.dependency_overrides[optional_principal] = lambda: None     # anonymous until a test signs in
    env.sign_in = lambda: env.app.dependency_overrides.__setitem__(optional_principal, lambda: env.principal)

    def remember(consent=True, **items):
        async def work(sessions):
            async with sessions() as s:
                await service.set_consent(s, env.customer, consent, NOW)
                for key, value in items.items():
                    await service.create(s, env.customer, MemoryCreate(idempotency_key="idem_" + uuid.uuid4().hex, category="preference", key=key,
                                                                         value=value, source="memory_page"), NOW)
                await s.commit()
        env.run(work)
    env.remember = remember
    env.saved = lambda: env.sql("select count(*) from memory_items")[0][0]
    return env


def ask(env, message):
    text = env.client.post("/v1/assistant/stream", json={"session_id": "s1", "idempotency_key": KEY, "message": message, "context": {}}).text
    return [(b.split("\n")[1][7:], json.loads(b.split("\n")[2][6:])) for b in text.strip().split("\n\n")]


names = lambda events: [d["name"] for e, d in events if e == "product"]
said = lambda events: " ".join(d["delta"] for e, d in events if e == "text")


def test_a_saved_colour_reorders_results_and_says_so(world):
    plain = names(ask(world, "shawl"))
    world.sign_in(); world.remember(favourite_colour="brown")
    events = ask(world, "shawl")
    assert set(names(events)[:2]) == {"Cocoa Shawl", "Walnut Shawl"} and names(events)[2] == "Ruby Shawl"   # preferred first, rest kept
    assert set(names(events)) == set(plain)                                                                # same results, only re-ordered
    assert "Using your saved preference (favourite colour brown)" in said(events)


def test_a_saved_budget_puts_affordable_items_first(world):
    world.sign_in(); world.remember(budget_max_pkr="3200")
    events = ask(world, "shawl")
    assert names(events)[0] == "Ruby Shawl" and "budget up to PKR 3200" in said(events)


def test_the_customers_own_colour_wins_over_the_saved_one(world):
    world.sign_in(); world.remember(favourite_colour="brown")
    events = ask(world, "red shawl")
    assert names(events) == ["Ruby Shawl"] and "saved preference" not in said(events)


def test_no_session_or_no_consent_means_no_personalisation(world):
    world.remember(favourite_colour="brown")                  # anonymous: memory exists but nobody is signed in
    assert "saved preference" not in said(ask(world, "shawl"))
    world.sign_in(); world.remember(consent=False)            # signed in, consent revoked: hidden again
    events = ask(world, "shawl")
    assert "saved preference" not in said(events) and names(events)[0] != "Cocoa Shawl"


def test_remember_proposes_the_parsed_value_and_saves_nothing(world):
    world.sign_in(); world.remember()
    events = ask(world, "remember I like brown")
    assert [d for e, d in events if e == "memory_suggestion"] == [{"key": "favourite_colour", "value": "brown"}]
    assert not names(events) and world.saved() == 0
    both = ask(world, "yaad rakho mujhe brown chahiye 4000 se kam")
    assert {d["key"] for e, d in both if e == "memory_suggestion"} == {"favourite_colour", "budget_max_pkr"}


def test_a_statement_of_taste_without_remember_is_never_proposed(world):
    world.sign_in(); world.remember()
    assert not [e for e, _ in ask(world, "I like brown shawls") if e == "memory_suggestion"]


def test_remember_explains_what_is_missing(world):
    assert "sign in" in said(ask(world, "remember I like brown")).lower()                 # anonymous
    world.sign_in(); world.remember(consent=False)
    assert "memory is off" in said(ask(world, "remember I like brown")).lower()           # signed in, not opted in
    world.remember()
    assert "what should i remember" in said(ask(world, "please remember this")).lower()   # nothing parseable
    assert world.saved() == 0


def test_memory_reaches_the_llm_only_when_the_whole_chain_is_cleared(world, monkeypatch):
    world.sign_in(); world.remember(favourite_colour="brown")
    monkeypatch.setattr(settings, "assistant_llm", True)
    free = StubGateway(models=["groq/some-model"])
    monkeypatch.setattr("assistant.grounded.get_gateway", lambda: free)
    ask(world, "shawl")
    assert "saved these preferences" not in free.prompts[-1] and free.calls[-1] == {"personal": False}      # free tier: memory kept out

    cleared = StubGateway(models=["acme/private-model"])
    monkeypatch.setattr(settings, "llm_provider_training_policies", "acme=no_training")
    monkeypatch.setattr(settings, "llm_free_tier_providers", "groq,gemini")
    monkeypatch.setattr("assistant.grounded.get_gateway", lambda: cleared)
    ask(world, "shawl")
    assert "favourite colour brown" in cleared.prompts[-1] and cleared.calls[-1] == {"personal": True}      # cleared: shared, personal chain

    monkeypatch.setattr(settings, "llm_provider_training_policies", "")
    ask(world, "shawl")
    assert "saved these preferences" not in cleared.prompts[-1]                                           # declaration removed: out again
