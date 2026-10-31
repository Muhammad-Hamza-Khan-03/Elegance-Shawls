"""/v1/search ranks with the configured embedder, keeps the same filters and response shape, and degrades when none is set."""
import asyncio

import pytest

from semantic.backfill import run_backfill
from semantic.embeddings import EmbeddingConfig, FakeEmbeddingProvider
from tests.integration.api_support import H, ApiEnv
from tests.integration.test_api_products import payload, variant

FAKE = FakeEmbeddingProvider(EmbeddingConfig("fake", "fake-hash-v1", 64))


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    e = ApiEnv(migrated_url, monkeypatch)
    for slug, colour in [("alpha", "Red"), ("beta", "Blue"), ("gamma", "Red")]:
        body = {**payload(slug), "name": f"{slug} shawl", "status": "active", "variants": [variant(slug, color=colour, price=1000, stock=2)]}
        assert e.client.post("/products/admin/", json=body, headers=H).status_code == 201
    e.run(lambda sessions: run_backfill(sessions, FAKE, worker_id="t"))
    return e


def slugs(env, **params):
    return [i["slug"] for i in env.client.get("/v1/search", params=params).json()["items"]]


def test_semantic_ranking_respects_hard_filters_and_paginates(env, monkeypatch):
    monkeypatch.setattr("routes.product_routes.get_embedder", lambda: FAKE)
    assert slugs(env, q="alpha shawl") [0] == "alpha"
    assert set(slugs(env, q="shawl", colour="red")) == {"alpha", "gamma"}   # semantic hits never bypass the filter
    first = env.client.get("/v1/search", params={"q": "shawl", "limit": 2}).json()
    second = env.client.get("/v1/search", params={"q": "shawl", "limit": 2, "cursor": first["next_cursor"]}).json()
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert env.client.get("/v1/search", params={"q": "shawl", "cursor": "garbage"}).status_code == 400


def test_without_an_embedder_search_stays_keyword_only(env, monkeypatch):
    monkeypatch.setattr("routes.product_routes.get_embedder", lambda: None)
    assert slugs(env, q="alpha") == ["alpha"]


def test_off_topic_queries_get_no_semantic_neighbours_but_shopping_words_are_trusted(env, monkeypatch):
    monkeypatch.setattr("routes.product_routes.get_embedder", lambda: FAKE)
    monkeypatch.setattr("configuration.config.settings.semantic_max_distance", 0.0)   # nothing is "close enough"
    assert slugs(env, q="delivery kitne din") == []                                  # no shopping word: neighbours dropped
    assert len(slugs(env, q="shawl")) == 3                                           # shopping word: ranking trusted, unchanged
