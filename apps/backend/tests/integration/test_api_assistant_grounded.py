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
