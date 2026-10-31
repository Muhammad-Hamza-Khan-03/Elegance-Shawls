"""The assistant remembers the conversation: follow-ups keep earlier colour, product type and budget (the reported transcript, replayed)."""
import json

import pytest

from assistant.grounded import catalogue_session
from configuration.config import settings
from database.pg import get_pg_session
from routes.assistant_routes import router as assistant_router
from tests.integration.api_support import H, ApiEnv
from tests.integration.test_api_products import payload, variant

KEY = "idem_" + "c" * 24

# (slug, name, category, [(colour, price, stock)])
CATALOGUE = [
    ("gray-shawl", "Checked Gray Wool Shawl", "shawls", [("Gray", 3500, 4)]),
    ("pink-shawl", "Jacquard Pink Wool Shawl", "shawls", [("Pink", 2400, 4)]),
    ("beige-shawl", "Fringed Beige Shawl", "shawls", [("Beige", 2400, 0)]),               # sold out
    ("blue-scarf", "Plain Blue Scarf", "scarves", [("Blue", 3500, 5), ("Gray", 3500, 5)]),  # matches grey only through its second variant
    ("maroon-scarf", "Checked Maroon Scarf", "scarves", [("Maroon", 2900, 5)]),
]


@pytest.fixture
def client(pg_engine_factory, migrated_url, monkeypatch):
    env = ApiEnv(migrated_url, monkeypatch)
    monkeypatch.setattr(settings, "assistant_catalogue", True)
    env.app.include_router(assistant_router)
    env.app.dependency_overrides[catalogue_session] = env.app.dependency_overrides[get_pg_session]
    for slug, name, category, variants in CATALOGUE:
        body = {**payload(slug), "name": name, "category": category, "status": "active",
                "variants": [variant(f"{c} {name}", color=c, price=p, stock=s) for c, p, s in variants]}
        assert env.client.post("/products/admin/", json=body, headers=H).status_code == 201, slug
    return env.client


def ask(client, message, *history):
    context = {f"prev_{i}": text for i, text in enumerate(history[-3:], start=1)}
    text = client.post("/v1/assistant/stream", json={"session_id": "s1", "idempotency_key": KEY, "message": message, "context": context}).text
    return [(b.split("\n")[1][7:], json.loads(b.split("\n")[2][6:])) for b in text.strip().split("\n\n")]


names = lambda events: sorted(d["name"] for e, d in events if e == "product")
said = lambda events: " ".join(d["delta"] for e, d in events if e == "text")


def test_the_reported_conversation(client):
    q1 = "show me shawls of grey under 2000"
    assert names(ask(client, q1)) == []                                                      # no grey shawl that cheap
    second = ask(client, "under 3000", q1)
    assert names(second) == [] and "Keeping what you asked before" in said(second)          # still grey shawls, still none <= 3000
    assert "colour grey" in said(second) and "shawl" in said(second)
    third = ask(client, "under 4000", q1, "under 3000")
    assert names(third) == ["Checked Gray Wool Shawl"]                                        # NOT the pink shawl or the maroon scarf
    fourth = ask(client, "grey color", q1, "under 3000", "under 4000")
    assert names(fourth) == ["Checked Gray Wool Shawl"] and "at most PKR 4000" in said(fourth)


def test_without_history_a_follow_up_has_nothing_to_keep(client):
    events = ask(client, "under 3000")
    assert {"Jacquard Pink Wool Shawl", "Checked Maroon Scarf"} <= set(names(events)) and "Keeping" not in said(events)


def test_the_card_shows_the_variant_that_matched_not_another_colour_of_the_product(client):
    events = ask(client, "grey scarf")
    blue_scarf = next(d for e, d in events if e == "product" and d["name"] == "Plain Blue Scarf")
    assert blue_scarf["color"] == "Gray" and blue_scarf["in_stock"] is True
    proposal = next(d for e, d in events if e == "proposal" and d["params"]["product_id"] == blue_scarf["product_id"])
    assert proposal["decision"]["outcome"] == "validated"


def test_a_sold_out_match_is_labelled_and_has_no_cart_suggestion(client):
    events = ask(client, "shawl under 3000")
    beige = next(d for e, d in events if e == "product" and d["name"] == "Fringed Beige Shawl")
    assert beige["in_stock"] is False
    assert beige["product_id"] not in {d["params"]["product_id"] for e, d in events if e == "proposal"}


def test_a_changed_topic_is_not_polluted_by_earlier_filters(client):
    events = ask(client, "delivery kitne din mein hoti hai", "grey shawl under 2000")
    assert names(events) == [] and "Keeping" not in said(events)


def test_cards_that_are_not_the_asked_type_are_framed_as_alternatives_and_exact_matches_and_stock_come_first(client):
    body = {**payload("stole-style"), "name": "Stole Style Wrap", "category": "shawls", "status": "active",
            "variants": [variant("Cream Wrap", color="Cream", price=3000, stock=2)]}
    assert client.post("/products/admin/", json=body, headers=H).status_code == 201     # matches the word "stole" but is a shawl
    events = ask(client, "stole")
    assert names(events) == ["Stole Style Wrap"] and "no exact stoles" in said(events).lower() and "closest alternatives" in said(events)

    exact = ask(client, "shawl under 3000")
    cards = [d["name"] for e, d in exact if e == "product"]
    assert "closest alternatives" not in said(exact)
    assert cards.index("Fringed Beige Shawl") > cards.index("Jacquard Pink Wool Shawl")   # the sold-out one comes last
