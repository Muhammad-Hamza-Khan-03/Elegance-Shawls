"""The assistant answers from the live catalogue: parsed filters, real prices/revisions, no invented products."""
import json

import pytest

from assistant.grounded import catalogue_session
from configuration.config import settings
from database.pg import get_pg_session
from routes.assistant_routes import router as assistant_router
from tests.integration.api_support import H, ApiEnv
from tests.integration.test_api_products import payload, variant

KEY = "idem_" + "a" * 24


@pytest.fixture
def client(pg_engine_factory, migrated_url, monkeypatch):
    env = ApiEnv(migrated_url, monkeypatch)
    monkeypatch.setattr(settings, "assistant_catalogue", True)
    env.app.include_router(assistant_router)
    env.app.dependency_overrides[catalogue_session] = env.app.dependency_overrides[get_pg_session]
    for slug, name, colour, price, stock in [("red-cheap", "Ruby Shawl", "Red", 1500, 3), ("red-dear", "Crimson Stole", "Red", 9000, 3),
                                             ("blue-cheap", "Navy Shawl", "Blue", 1500, 3), ("red-sold-out", "Rose Shawl", "Red", 1200, 0)]:
        body = {**payload(slug), "name": name, "status": "active", "variants": [variant(name, color=colour, price=price, stock=stock)]}
        assert env.client.post("/products/admin/", json=body, headers=H).status_code == 201
    return env.client


def ask(client, message):
    text = client.post("/v1/assistant/stream", json={"session_id": "s1", "idempotency_key": KEY, "message": message, "context": {}}).text
    return [(block.split("\n")[1][7:], json.loads(block.split("\n")[2][6:])) for block in text.strip().split("\n\n")]


def test_filters_come_from_the_message_and_cards_from_the_database(client):
    events = ask(client, "red shawl under 2000 in stock")
    names = [d["name"] for e, d in events if e == "product"]
    assert names == ["Ruby Shawl"]
    assert events[-1][0] == "done"
    proposal = next(d for e, d in events if e == "proposal")
    assert proposal["decision"]["outcome"] == "validated" and proposal["params"]["expected_unit_price"] == 1500


def test_no_match_says_so_and_proposes_nothing(client):
    events = ask(client, "green shawl")
    assert not [e for e, _ in events if e in ("product", "proposal")] and events[-1][0] == "done"


class StubGateway:
    def __init__(self, text=None, fail=False):
        self.text, self.fail, self.prompts = text, fail, []

    async def complete(self, messages, **_):
        self.prompts.append(messages)
        if self.fail:
            raise RuntimeError("all providers down")
        return type("R", (), {"text": self.text})()


def with_llm(monkeypatch, gateway):
    monkeypatch.setattr(settings, "assistant_llm", True)
    monkeypatch.setattr("assistant.grounded.get_gateway", lambda: gateway)


def test_llm_writes_the_wording_but_cards_and_proposals_stay_database_driven(client, monkeypatch):
    gateway = StubGateway("Ye raha aap ke liye ek khoobsurat shawl. Invented Product PKR 1 is also great!")
    with_llm(monkeypatch, gateway)
    events = ask(client, "red shawl under 2000 in stock")
    assert [d["name"] for e, d in events if e == "product"] == ["Ruby Shawl"]  # the invented product is only words
    assert next(d for e, d in events if e == "text")["delta"].startswith("Ye raha")
    assert "Ruby Shawl: PKR 1500" in gateway.prompts[0][1]["content"]
    assert "red shawl" in gateway.prompts[0][1]["content"] and gateway.prompts[0][0]["role"] == "system"


def test_llm_failure_falls_back_to_the_fixed_sentence(client, monkeypatch):
    with_llm(monkeypatch, StubGateway(fail=True))
    events = ask(client, "red shawl under 2000 in stock")
    assert next(d for e, d in events if e == "text")["delta"] == "I found 1 that match. "
    assert events[-1][0] == "done"


def test_llm_answers_when_nothing_matches_without_proposing_anything(client, monkeypatch):
    with_llm(monkeypatch, StubGateway("Sorry, we do not have green right now."))
    events = ask(client, "green shawl")
    assert next(d for e, d in events if e == "text")["delta"].startswith("Sorry")
    assert not [e for e, _ in events if e in ("product", "proposal")]


def ask_voice(client, message):
    text = client.post("/v1/assistant/stream", json={"session_id": "s1", "idempotency_key": KEY, "message": message,
                                                      "context": {"input": "voice"}}).text
    return [(block.split("\n")[1][7:], json.loads(block.split("\n")[2][6:])) for block in text.strip().split("\n\n")]


def test_voice_input_uses_the_bridge_and_still_answers_from_the_database(client):
    events = ask_voice(client, "red shawl under 2000 in stock")
    assert [d["name"] for e, d in events if e == "product"] == ["Ruby Shawl"]


def test_uncertain_or_negated_speech_asks_again_instead_of_guessing(client):
    for heard in ("red shawl not under 2000", "red shawl under maybe two or three thousand"):
        events = ask_voice(client, heard)
        assert not [e for e, _ in events if e in ("product", "proposal")], heard
        assert "say it again" in next(d for e, d in events if e == "text")["delta"], heard
