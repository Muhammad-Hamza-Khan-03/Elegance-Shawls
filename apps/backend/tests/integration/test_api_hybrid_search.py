"""Hybrid keyword+semantic /v1/search with the deterministic fake embedder on a real PostgreSQL."""
import pytest

from routes.product_routes import get_fusion_weights, get_query_embedder
from semantic.backfill import run_backfill
from semantic.embeddings import EmbeddingConfig, FakeEmbeddingProvider
from semantic.fusion import FusionWeights
from tests.integration.api_support import H, ApiEnv
from tests.integration.test_api_products import payload, variant

PROVIDER = FakeEmbeddingProvider(EmbeddingConfig("fake", "fake-hash-v1", 64))


class Broken:
    config = PROVIDER.config

    def embed(self, text):
        raise TimeoutError("provider down")


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    return ApiEnv(migrated_url, monkeypatch)


def make(env, slug, name, variants=None, status="active", **over):
    body = {**payload(slug), "name": name, "status": status, **over}
    if variants:
        body["variants"] = variants
    r = env.client.post("/products/admin/", json=body, headers=H)
    assert r.status_code == 201, r.text
    return r.json()["_id"]


def embed_all(env):
    async def work(sessions):
        return await run_backfill(sessions, PROVIDER, worker_id="t", limit=100)
    env.run(work)


def use(env, provider=PROVIDER, weights=None):
    env.app.dependency_overrides[get_query_embedder] = lambda: provider
    if weights:
        env.app.dependency_overrides[get_fusion_weights] = lambda: weights


def walk(env, limit=100, **params):
    slugs, cursor, modes = [], None, set()
    while True:
        r = env.client.get("/v1/search", params={"limit": limit, **params, **({"cursor": cursor} if cursor else {})})
        assert r.status_code == 200, r.text
        modes.add(r.headers.get("X-Search-Mode"))
        body = r.json()
        slugs += [i["slug"] for i in body["items"]]
        cursor = body["next_cursor"]
        if not cursor:
            return slugs, modes


def seed_words(env):
    make(env, "both", "Wool Silk Shawl")
    make(env, "wool-only", "Wool Wrap")
    make(env, "silk-only", "Silk Scarf")
    make(env, "unrelated", "Cotton Stole")
    embed_all(env)


def test_hybrid_unions_lexical_and_semantic_and_ranks_agreement_first(env):
    seed_words(env)
    lexical, lmodes = walk(env, q="wool silk")
    assert lexical == ["both"] and lmodes == {None}             # no embedder: unchanged lexical contract
    use(env)
    hybrid, modes = walk(env, q="wool silk")
    assert modes == {"hybrid"} and hybrid[0] == "both"
    assert {"wool-only", "silk-only"} <= set(hybrid)             # semantic-only candidates are admitted
    assert hybrid == walk(env, q="wool silk")[0]                 # deterministic


def test_zero_semantic_weight_equals_keyword_only(env):
    seed_words(env)
    use(env, weights=FusionWeights(1, 0))
    assert walk(env, q="wool silk")[0] == ["both"]


def test_hard_filters_hold_for_semantically_best_products(env):
    trap = make(env, "trap", "Red Wool Shawl", [variant("Red", price=1000, stock=0), variant("Blue", price=9000, stock=5)])
    make(env, "ok", "Wool Shawl", [variant("Red", price=1000, stock=3)])
    make(env, "draft", "Red Wool Shawl", status="draft")
    gone = make(env, "gone", "Red Wool Shawl")
    embed_all(env)
    assert env.client.delete(f"/products/admin/{gone}", headers=H).status_code == 200   # embedding row still exists
    use(env)
    params = dict(q="red wool shawl", colour="red", max_price=2000, in_stock=True)
    slugs, modes = walk(env, **params)
    assert slugs == ["ok"] and modes == {"hybrid"}                # trap has each attribute, but not on one variant
    assert "trap" in walk(env, q="red wool shawl")[0] and trap
    assert {"draft", "gone"}.isdisjoint(walk(env, q="red wool shawl")[0])


def test_stale_embedding_is_not_a_semantic_candidate(env):
    seed_words(env)
    use(env)
    env.sql("update product_embeddings set content_hash = repeat('0', 64)")
    assert walk(env, q="wool silk")[0] == ["both"]               # only lexical remains


def test_lexical_fallback_when_embeddings_unavailable_or_failing(env):
    seed_words(env)
    expected = walk(env, q="wool")[0]
    for provider in (None, Broken()):
        use(env, provider)
        slugs, modes = walk(env, q="wool")
        assert slugs == expected and modes == {None}
    use(env)
    env.sql("delete from product_embeddings")                    # nothing embedded: hybrid degrades to keyword ranking
    assert walk(env, q="wool")[0] == expected


def test_pagination_is_complete_stable_bound_and_honest(env):
    for i in range(7):
        make(env, f"wool-{i}", f"Wool Shawl {i}")
    embed_all(env)
    use(env)
    full, _ = walk(env, q="wool shawl")
    paged, modes = walk(env, limit=2, q="wool shawl")
    assert paged == full and len(set(full)) == 7 and modes == {"hybrid"}
    cursor = env.client.get("/v1/search", params={"q": "wool shawl", "limit": 2}).json()["next_cursor"]
    get = lambda **p: env.client.get("/v1/search", params={"limit": 2, **p}).status_code  # noqa: E731
    assert get(q="wool shawl", cursor=cursor) == 200
    assert get(q="wool shawl", cursor=cursor[:-1] + ("0" if cursor[-1] != "0" else "1")) == 400
    assert get(q="silk", cursor=cursor) == 400                    # cursor replayed against another query
    assert get(q="wool shawl", colour="red", cursor=cursor) == 400
    keyset = env.client.get("/v1/search", params={"limit": 2}).json()["next_cursor"]
    assert get(q="wool shawl", cursor=keyset) == 400              # keyset cursor is not valid for ranked results
    use(env, None)
    assert get(q="wool shawl", cursor=cursor) == 400              # embeddings went away: cannot continue honestly
    assert set(env.client.get("/v1/search", params={"q": "wool"}).json()) == {"items", "next_cursor"}
