"""GET /v1/search ranks with the canonical embeddings, keeps the same filters and response shape, and degrades without them."""
import pytest

from configuration.config import settings
from models.relational_model import EMBEDDING_DIMENSIONS
from repositories.hybrid import QueryEmbedding
from search import embedding_service as svc
from search.providers import FakeEmbeddingProvider
from tests.integration.api_support import H, ApiEnv
from tests.integration.repo_helpers import tx
from tests.integration.test_api_products import payload, variant

INDEX = "idx-api-semantic"
FAKE = FakeEmbeddingProvider(EMBEDDING_DIMENSIONS)


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    monkeypatch.setattr(settings, "embedding_index_version", INDEX)
    e = ApiEnv(migrated_url, monkeypatch)
    for slug, colour in [("alpha", "Red"), ("beta", "Blue"), ("gamma", "Red")]:
        body = {**payload(slug), "name": f"{slug} shawl", "status": "active", "variants": [variant(slug, color=colour, price=1000, stock=2)]}
        assert e.client.post("/products/admin/", json=body, headers=H).status_code == 201
    ids = {r[1]: r[0] for r in e.sql("SELECT id, slug FROM products")}

    async def embed_all(sessions):
        for owner in ids.values():
            async with tx(sessions) as s:
                row, _ = await svc.ensure_pending(s, "product", owner, FAKE, index_version=INDEX, max_attempts=3)
            await svc.process(sessions, FAKE, "product", row.id, lease_seconds=60, backoff_seconds=0)
        async with sessions() as s:
            source = await svc.load_source(s, "product", ids["alpha"])
        return (await FAKE.embed([source.representation.text]))[0]

    e.alpha_vector = e.run(embed_all)
    return e


def pinned(env, monkeypatch):
    async def embed_query(text):
        return QueryEmbedding(FAKE, env.alpha_vector)
    monkeypatch.setattr("routes.product_routes.embed_query", embed_query)


def slugs(env, **params):
    return [i["slug"] for i in env.client.get("/v1/search", params=params).json()["items"]]


def test_semantic_ranking_respects_hard_filters_and_paginates(env, monkeypatch):
    pinned(env, monkeypatch)
    assert slugs(env, q="alpha shawl")[0] == "alpha"
    assert set(slugs(env, q="shawl", colour="red")) == {"alpha", "gamma"}   # semantic hits never bypass the filter
    first = env.client.get("/v1/search", params={"q": "shawl", "limit": 2}).json()
    second = env.client.get("/v1/search", params={"q": "shawl", "limit": 2, "cursor": first["next_cursor"]}).json()
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert env.client.get("/v1/search", params={"q": "shawl", "cursor": "garbage"}).status_code == 400


def test_without_an_embedding_search_stays_keyword_only(env, monkeypatch):
    async def none(text):
        return None
    monkeypatch.setattr("routes.product_routes.embed_query", none)
    assert slugs(env, q="alpha") == ["alpha"]


def test_off_topic_queries_get_no_semantic_neighbours_but_shopping_words_are_trusted(env, monkeypatch):
    pinned(env, monkeypatch)
    monkeypatch.setattr(settings, "semantic_max_distance", -1.0)  # nothing is "close enough"
    assert slugs(env, q="delivery kitne din") == []                # no shopping word: neighbours dropped
    assert len(slugs(env, q="shawl")) == 3                         # shopping word: ranking trusted, unchanged
