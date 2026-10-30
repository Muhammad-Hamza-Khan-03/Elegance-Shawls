"""POST /v1/search/hybrid on real PostgreSQL + pgvector with the offline fake embedding provider (no network)."""
import pytest

from configuration.config import settings
from models.relational_model import EMBEDDING_DIMENSIONS
from repositories import products as products_repo
from routes.search_routes import router as search_router
from search import embedding_service as svc
from search import hybrid
from search.providers import FakeEmbeddingProvider, NonRetryableEmbeddingError
from tests.integration.api_support import ApiEnv
from tests.integration.repo_helpers import tx
from tests.integration.test_api_products import variant
from tests.integration.test_api_search import add, slugs

INDEX = "idx-hybrid-test"
TABLES = ("products", "variants", "product_embeddings", "variant_embeddings", "staged_products", "events")


class Pinned(FakeEmbeddingProvider):
    """The query embeds to the vector of `target` text, so the nearest stored vector is exactly known."""
    def __init__(self, target):
        super().__init__(EMBEDDING_DIMENSIONS)
        self.target = target

    async def embed(self, texts):
        return await super().embed([self.target for _ in texts])


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    env = ApiEnv(migrated_url, monkeypatch)
    env.app.include_router(search_router)
    monkeypatch.setattr(settings, "embedding_enabled", True)
    monkeypatch.setattr(settings, "embedding_provider", "fake")
    monkeypatch.setattr(settings, "embedding_index_version", INDEX)
    return env


def pid(env, slug):
    return env.sql("SELECT id FROM products WHERE slug = :s", s=slug)[0][0]


def embed(env, *slugs_):
    """Embed the product-level representation of each product, as the S4b worker would."""
    owners = [pid(env, slug) for slug in slugs_]

    async def work(sessions):
        for owner in owners:
            async with tx(sessions) as s:
                row, _ = await svc.ensure_pending(s, "product", owner, FakeEmbeddingProvider(EMBEDDING_DIMENSIONS),
                                                  index_version=INDEX, max_attempts=3)
            assert (await svc.process(sessions, FakeEmbeddingProvider(EMBEDDING_DIMENSIONS), "product", row.id,
                                      lease_seconds=60, backoff_seconds=0))["status"] == "succeeded"
    env.run(work)


def text_of(env, slug):
    owner = pid(env, slug)

    async def work(sessions):
        async with sessions() as s:
            return (await svc.load_source(s, "product", owner)).representation.text
    return env.run(work)


def pin(env, monkeypatch, slug):
    target = env.texts[slug]
    monkeypatch.setattr(hybrid, "provider_for", lambda name, dims: Pinned(target))


def seed(env):
    add(env, "wool-brown", "Brown Cozy Stole", "stoles", [variant("Brown", price=3000)])
    add(env, "cashmere", "Cashmere Wrap", "stoles", [variant("Brown", price=3500), variant("Black", price=3600)])
    add(env, "pricey", "Luxury Stole", "stoles", [variant("Brown", price=9000)])
    add(env, "gone", "Old Cashmere Stole", "stoles", [variant("Brown", price=2000)])
    embed(env, "wool-brown", "cashmere", "pricey", "gone")
    env.texts = {slug: text_of(env, slug) for slug in ("wool-brown", "cashmere", "pricey", "gone")}   # before "gone" is archived
    gone = pid(env, "gone")
    env.run(lambda sessions: archive(sessions, gone))


async def archive(sessions, product_id):
    async with tx(sessions) as s:
        await products_repo.archive_product(s, product_id)


def post(env, q="cozy stole under 4000", **body):
    return env.client.post("/v1/search/hybrid", json={"q": q, **body})


def test_lexical_and_vector_candidates_are_unioned_under_exact_filters(env, monkeypatch):
    seed(env)
    pin(env, monkeypatch, "cashmere")                     # nearest vector: a product with no "wool" word
    body = post(env).json()
    assert body["semantic"] is True and set(slugs(body)) == {"wool-brown", "cashmere"}
    assert body["filters"] == {"category": "stoles", "max_price": 4000} and body["text"] == ["cozy"]
    cashmere = next(i for i in body["items"] if i["product"]["slug"] == "cashmere")
    assert [v["_id"] for v in cashmere["product"]["variants"] if v["price"] <= 4000] and len(cashmere["matched_variant_ids"]) == 2
    assert "rank" not in str(body) and "score" not in str(body)             # branch ranks stay internal


def test_vectors_cannot_bypass_filters_archive_or_staleness(env, monkeypatch):
    seed(env)
    for slug in ("pricey", "gone"):                       # over budget / archived: their vectors are the nearest
        pin(env, monkeypatch, slug)
        assert not {"pricey", "gone"} & set(slugs(post(env).json()))     # only eligible products are ever ranked
    pin(env, monkeypatch, "cashmere")
    assert "cashmere" in slugs(post(env).json())
    owner = pid(env, "cashmere")
    env.run(lambda sessions: bump(sessions, owner))             # source moved on: the vector is stale
    assert slugs(post(env).json()) == ["wool-brown"]
    assert post(env, "cozy stole not over 1000").json()["items"] == []


async def bump(sessions, product_id):
    async with tx(sessions) as s:
        variant_id = (await products_repo.get_product(s, product_id)).variants[0].id
        await products_repo.set_variant_stock(s, product_id, variant_id, 9)


def test_semantic_branch_is_omitted_when_disabled_or_unknown(env, monkeypatch):
    seed(env)
    for key, value in (("embedding_enabled", False), ("embedding_provider", "openai"), ("embedding_provider", "")):
        monkeypatch.setattr(settings, key, value)
        body = post(env).json()
        assert body["semantic"] is False and slugs(body) == ["wool-brown"]
        monkeypatch.setattr(settings, "embedding_enabled", True)
        monkeypatch.setattr(settings, "embedding_provider", "fake")


def test_paging_cursor_rejections_and_isolation_from_the_deterministic_endpoint(env, monkeypatch):
    seed(env)
    pin(env, monkeypatch, "cashmere")
    first = post(env, limit=1).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = post(env, limit=1, cursor=first["next_cursor"]).json()
    assert second["next_cursor"] is None and sorted(slugs(first) + slugs(second)) == ["cashmere", "wool-brown"]
    assert post(env, limit=1, cursor=first["next_cursor"]).json() == second                        # repeatable
    for bad in (dict(q="cozy stole under 5000"), dict(q="silk stole under 4000")):
        assert post(env, cursor=first["next_cursor"], **bad).status_code == 400
    assert post(env, cursor=first["next_cursor"][:-2] + "00").status_code == 400
    monkeypatch.setattr(settings, "embedding_index_version", "idx-other")                           # index version changed
    assert post(env, cursor=first["next_cursor"]).status_code == 400
    monkeypatch.setattr(settings, "embedding_index_version", INDEX)
    det = env.client.post("/v1/search", json={"q": "stole", "limit": 1}).json()["next_cursor"]
    assert post(env, "stole", cursor=det).status_code == 400
    assert env.client.post("/v1/search", json={"q": "stole", "cursor": first["next_cursor"]}).status_code == 400
    assert post(env, model="x").status_code == 422 and post(env, offset=1).status_code == 422       # no client selectors/offset


def test_hybrid_search_never_writes_and_leaves_deterministic_search_unchanged(env, monkeypatch):
    seed(env)
    pin(env, monkeypatch, "cashmere")
    before = [env.sql(f"SELECT count(*), md5(string_agg(t::text, ',' ORDER BY t::text)) FROM {t} t")[0] for t in TABLES]
    for q in ("cozy stole", "", "zzzz", "'; DROP TABLE products;--", "stole not over 1000", "100%_"):
        assert post(env, q).status_code == 200
    assert [env.sql(f"SELECT count(*), md5(string_agg(t::text, ',' ORDER BY t::text)) FROM {t} t")[0] for t in TABLES] == before
    det = env.client.post("/v1/search", json={"q": "cozy stole under 4000"}).json()
    assert slugs(det) == ["wool-brown"] and set(det) == {"items", "next_cursor", "filters", "text", "unsupported"}


# ---- local_e5 path (flagged, local-only); the model is replaced by a pinned stub carrying the local_e5 identity ----

class LocalStub(Pinned):
    name, model, model_revision = "local_e5", "intfloat/multilingual-e5-base", "b" * 64


def seed_local(env):
    add(env, "wool-brown", "Brown Cozy Stole", "stoles", [variant("Brown", price=3000)])
    add(env, "cashmere", "Cashmere Wrap", "stoles", [variant("Brown", price=3500), variant("Black", price=3600)])
    add(env, "pricey", "Luxury Stole", "stoles", [variant("Brown", price=9000)])
    add(env, "unindexed", "Cozy Unindexed Stole", "stoles", [variant("Brown", price=2500)])   # no vector: never semantic
    owners = [pid(env, s) for s in ("wool-brown", "cashmere", "pricey")]

    async def work(sessions):
        for owner in owners:
            async with tx(sessions) as s:
                row, _ = await svc.ensure_pending(s, "product", owner, LocalStub("x"), index_version=INDEX, max_attempts=3)
            assert (await svc.process(sessions, LocalStub("x"), "product", row.id, lease_seconds=60,
                                      backoff_seconds=0))["status"] == "succeeded"
    env.run(work)
    env.texts = {s: text_of(env, s) for s in ("wool-brown", "cashmere", "pricey")}


def local_env(env, monkeypatch, nearest="cashmere"):
    for key, value in {"local_semantic_search_enabled": True, "embedding_provider": "local_e5", "environment": "development"}.items():
        monkeypatch.setattr(settings, key, value)
    seed_local(env)
    near(env, monkeypatch, nearest)


def near(env, monkeypatch, slug):
    monkeypatch.setattr(hybrid.local_e5, "local_provider", lambda kind="query": LocalStub(env.texts[slug]))


def test_local_flag_on_ranks_semantically_under_hard_constraints_and_excludes_stale(env, monkeypatch):
    local_env(env, monkeypatch, "pricey")                  # the nearest vector belongs to an over-budget product
    body = post(env).json()
    assert body["semantic"] is True and "pricey" not in slugs(body) and "unindexed" in slugs(body)
    near(env, monkeypatch, "cashmere")
    assert set(slugs(post(env).json())) == {"wool-brown", "unindexed", "cashmere"}
    owner = pid(env, "cashmere")
    env.run(lambda sessions: bump(sessions, owner))                 # source moved on: the vector is dropped at once
    assert "cashmere" not in slugs(post(env).json())
    assert post(env, "cozy stole not over 1000").json()["items"] == []


def test_local_flag_off_or_non_local_environment_is_lexical_only(env, monkeypatch):
    seed_local(env)
    monkeypatch.setattr(settings, "embedding_provider", "local_e5")
    body = post(env).json()
    baseline = slugs(body)
    assert body["semantic"] is False and baseline == ["unindexed", "wool-brown"]   # flag off (default): real gate refuses
    monkeypatch.setattr(settings, "local_semantic_search_enabled", True)
    for name in ("production", "staging"):
        monkeypatch.setattr(settings, "environment", name)
        body = post(env).json()
        assert body["semantic"] is False and slugs(body) == baseline


def test_local_provider_failure_falls_back_and_cursors_do_not_cross_modes(env, monkeypatch):
    local_env(env, monkeypatch)
    first = post(env, limit=1).json()
    assert first["semantic"] is True and first["next_cursor"]
    assert post(env, limit=1, cursor=first["next_cursor"]).status_code == 200

    class Broken(LocalStub):
        async def embed(self, texts):
            raise NonRetryableEmbeddingError("boom")
    monkeypatch.setattr(hybrid.local_e5, "local_provider", lambda kind="query": Broken("x"))
    body = post(env).json()
    assert body["semantic"] is False and set(slugs(body)) == {"wool-brown", "unindexed"}
    assert post(env, limit=1, cursor=first["next_cursor"]).status_code == 400          # semantic cursor, lexical mode
    near(env, monkeypatch, "cashmere")
    monkeypatch.setattr(LocalStub, "model_revision", "c" * 64)                          # model revision change
    assert post(env, limit=1, cursor=first["next_cursor"]).status_code == 400


def test_local_path_never_writes(env, monkeypatch):
    local_env(env, monkeypatch)
    before = [env.sql(f"SELECT count(*), md5(string_agg(t::text, ',' ORDER BY t::text)) FROM {t} t")[0] for t in TABLES]
    for q in ("cozy stole", "", "zzzz", "stole not over 1000"):
        assert post(env, q).status_code == 200
    assert [env.sql(f"SELECT count(*), md5(string_agg(t::text, ',' ORDER BY t::text)) FROM {t} t")[0] for t in TABLES] == before
