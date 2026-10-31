"""Weighted hybrid retrieval (GET /v1/search, assistant) over the canonical product/variant embeddings, on real
PostgreSQL + pgvector with the offline fake provider. Vectors are written by search.embedding_service, the same path the
worker and backfill use; the fake has no semantics, so a query is "pinned" to the representation text of a known product."""
import pytest
from sqlalchemy import text

from configuration.config import settings
from models.relational_model import EMBEDDING_DIMENSIONS
from repositories import products as catalogue
from repositories.hybrid import QueryEmbedding, embed_query, hybrid_search
from repositories.products import VariantFilter, VariantInput
from search import embedding_service as svc
from search import hybrid as search_hybrid
from search.providers import FakeEmbeddingProvider
from semantic.ranking import normalize_weights
from tests.integration.repo_helpers import product_input, run_repo, tx
from utils.pagination import encode_cursor

INDEX = "idx-hybrid-repo"
FAKE = FakeEmbeddingProvider(EMBEDDING_DIMENSIONS)


@pytest.fixture(autouse=True)
def index_version(monkeypatch):
    monkeypatch.setattr(settings, "embedding_index_version", INDEX)


def v(name, price, stock, color=None):
    return VariantInput(name=name, color=color or name, image_url="https://img.example/v.jpg", price=price, stock=stock)


async def embed(sessions, kind, owner):
    async with tx(sessions) as s:
        row, _ = await svc.ensure_pending(s, kind, owner, FAKE, index_version=INDEX, max_attempts=3)
    assert (await svc.process(sessions, FAKE, kind, row.id, lease_seconds=60, backoff_seconds=0))["status"] == "succeeded"


async def make(sessions, slug, name, variants, embedded=True, **over):
    async with tx(sessions) as s:
        p = await catalogue.create_product(s, product_input(slug, name=name, status="active", variants=variants, **over))
        variant_ids = [x.id for x in p.variants]
    if embedded:
        await embed(sessions, "product", p.id)
        for vid in variant_ids:
            await embed(sessions, "variant", vid)
    return p.id


async def near(sessions, product_id) -> QueryEmbedding:
    """A query whose vector equals the product's own stored vector: it is the unique nearest neighbour."""
    async with sessions() as s:
        source = await svc.load_source(s, "product", product_id)
    return QueryEmbedding(FAKE, (await FAKE.embed([source.representation.text]))[0])


async def search(sessions, **kw):
    async with sessions() as s:
        return await hybrid_search(s, **{"limit": 20, **kw})


def test_semantic_candidates_never_bypass_hard_filters(pg_engine_factory):
    async def scenario(sessions):
        ok = await make(sessions, "ok", "Ok", [v("Red", 4000, 3)])
        split = await make(sessions, "split", "Split", [v("Red", 4000, 0), v("Blue", 9000, 5)])  # no single red+in-stock variant
        pricey = await make(sessions, "pricey", "Pricey", [v("Red", 99000, 3)])
        archived = await make(sessions, "archived", "Archived", [v("Red", 4000, 3)])
        stale = await make(sessions, "stale", "Stale", [v("Red", 4000, 3)])
        await make(sessions, "plain", "Plain", [v("Red", 4000, 3)], embedded=False)
        async with tx(sessions) as s:
            await catalogue.archive_product(s, archived)
            await catalogue.set_variant_stock(s, stale, (await catalogue.get_product(s, stale)).variants[0].id, 1)  # revision bump
        q = await near(sessions, ok)
        everything = await search(sessions, q="shawls", embedding=q)
        assert everything.mode == "hybrid"
        assert {p.id for p in everything.items} == {ok, split, pricey}  # archived/stale/unembedded semantic hits are out
        f = VariantFilter(colour="red", max_price=5000, in_stock=True)
        filtered = await search(sessions, q="shawls", embedding=q, variant=f)
        assert [p.id for p in filtered.items] == [ok]
        lexical = await search(sessions, q="ok", variant=f)  # same filter, lexical-only: identical visibility rules
        assert lexical.mode == "lexical" and [p.id for p in lexical.items] == [ok]
        assert (await search(sessions, q="archived")).items == []

    run_repo(pg_engine_factory, scenario)


def test_content_change_at_the_same_revision_drops_the_vector(pg_engine_factory):
    async def scenario(sessions):
        a = await make(sessions, "a", "Alpha", [v("Red", 100, 1)])
        q = await near(sessions, a)
        assert [p.id for p in (await search(sessions, q="shawls", embedding=q)).items] == [a]
        async with tx(sessions) as s:  # bypasses the revision bump on purpose: only the content hash can notice
            await s.execute(text("UPDATE products SET name = 'Rewritten' WHERE id = :i"), {"i": a})
        assert (await search(sessions, q="shawls", embedding=q)).items == []

    run_repo(pg_engine_factory, scenario)


def test_vectors_of_another_model_or_index_are_never_compared(pg_engine_factory, monkeypatch):
    class OtherModel(FakeEmbeddingProvider):
        model = "fake-other-model"

    async def scenario(sessions):
        a = await make(sessions, "a", "Alpha", [v("Red", 100, 1)])
        q = await near(sessions, a)
        other = QueryEmbedding(OtherModel(EMBEDDING_DIMENSIONS), q.vector)
        assert (await search(sessions, q="shawls", embedding=other)).items == []          # other model: no rows in that space
        monkeypatch.setattr(settings, "embedding_index_version", "idx-other")
        assert (await search(sessions, q="shawls", embedding=q)).items == []              # other index version
        monkeypatch.setattr(settings, "embedding_index_version", INDEX)
        assert [p.id for p in (await search(sessions, q="shawls", embedding=q)).items] == [a]

    run_repo(pg_engine_factory, scenario)


def test_zero_or_invalid_stored_vectors_are_dropped(pg_engine_factory):
    async def scenario(sessions):
        a = await make(sessions, "a", "Alpha", [v("Red", 100, 1)])
        q = await near(sessions, a)
        async with tx(sessions) as s:
            await s.execute(text("UPDATE product_embeddings SET embedding = array_fill(0, ARRAY[768])::vector WHERE product_id = :i"), {"i": a})
            await s.execute(text("UPDATE variant_embeddings SET embedding = array_fill(0, ARRAY[768])::vector WHERE product_id = :i"), {"i": a})
        assert (await search(sessions, q="shawls", embedding=q)).items == []   # cosine distance is NaN: not a neighbour

    run_repo(pg_engine_factory, scenario)


def test_lexical_fallback_when_semantic_unavailable(pg_engine_factory, monkeypatch):
    async def scenario(sessions):
        a = await make(sessions, "a", "Shawls Alpha", [v("Red", 100, 1)])
        await make(sessions, "b", "Other", [v("Red", 100, 1)])
        q = await near(sessions, a)
        assert (await search(sessions, q="shawls", embedding=None)).mode == "lexical"
        assert (await search(sessions, q="shawls", embedding=q)).mode == "hybrid"
        assert (await search(sessions, q="  ", embedding=q)).mode == "lexical"  # nothing to embed
        assert [p.id for p in (await search(sessions, q="shawls", embedding=None)).items] == [a]

    run_repo(pg_engine_factory, scenario)


def test_embed_query_degrades_to_none(monkeypatch):
    import asyncio

    class Down(FakeEmbeddingProvider):
        async def embed(self, texts):
            raise ConnectionError("provider down")

    class WrongDims(FakeEmbeddingProvider):
        async def embed(self, texts):
            return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr(settings, "embedding_provider", "fake")
    monkeypatch.setattr(settings, "embedding_enabled", False)
    assert asyncio.run(embed_query("shawls")) is None                                      # disabled
    monkeypatch.setattr(settings, "embedding_enabled", True)
    assert asyncio.run(embed_query("   ")) is None                                         # blank
    got = asyncio.run(embed_query("shawls"))
    assert got is not None and len(got.vector) == EMBEDDING_DIMENSIONS and got.provider.model == FAKE.model
    for broken in (Down, WrongDims):
        monkeypatch.setattr(search_hybrid, "provider_for", lambda name, dims, b=broken: b(dims))
        assert asyncio.run(embed_query("shawls")) is None                                  # provider failure / invalid vector
    monkeypatch.undo()   # real provider_for again
    monkeypatch.setattr(settings, "embedding_enabled", True)
    monkeypatch.setattr(settings, "embedding_provider", "nonexistent")
    assert asyncio.run(embed_query("shawls")) is None                                      # unknown provider fails closed


def test_fusion_weights_and_repeatability(pg_engine_factory):
    async def scenario(sessions):
        both = await make(sessions, "both", "Shawls Wrap", [v("Red", 100, 1)])
        lex = await make(sessions, "lex", "Shawls Wrap Two", [v("Red", 100, 1)], embedded=False)
        sem = await make(sessions, "sem", "Plain", [v("Red", 100, 1)])
        q = await near(sessions, sem)
        runs = [[p.id for p in (await search(sessions, q="shawls", embedding=q)).items] for _ in range(3)]
        assert runs[0] == runs[1] == runs[2] and set(runs[0]) == {both, lex, sem}
        lex_only = await search(sessions, q="shawls", embedding=q, weights=normalize_weights(1, 0))
        assert [p.id for p in lex_only.items][-1] == sem
        sem_only = await search(sessions, q="shawls", embedding=q, weights=normalize_weights(0, 1))
        assert [p.id for p in sem_only.items][0] == sem and [p.id for p in sem_only.items][-1] == lex

    run_repo(pg_engine_factory, scenario)


@pytest.mark.parametrize("use_embedding", [False, True])
def test_pages_are_stable_complete_and_cursors_strict(pg_engine_factory, use_embedding):
    async def scenario(sessions):
        ids = [await make(sessions, f"s{i}", f"Shawls {i}", [v("Red", 100, 1)], embedded=bool(i % 2)) for i in range(5)]
        q = await near(sessions, ids[1]) if use_embedding else None
        kw = {"q": "shawls", "embedding": q}
        full = [p.id for p in (await search(sessions, **kw)).items]
        seen, cursor, pages, first_cursor = [], None, 0, None
        while True:
            page = await search(sessions, limit=2, cursor=cursor, **kw)
            seen += [p.id for p in page.items]
            pages += 1
            cursor = page.next_cursor
            if cursor is None:
                break
            first_cursor = first_cursor or cursor
        assert seen == full and len(set(seen)) == len(seen) >= 5 and pages == 3
        assert (await search(sessions, limit=len(full), **kw)).next_cursor is None  # exact fit: no phantom page
        async with sessions() as s:
            p = (await catalogue.list_products(s, public=True, limit=1)).items[0]
        for c in [first_cursor[:-1], first_cursor + "x", "garbage", encode_cursor(p.created_at, p.id)]:
            with pytest.raises(ValueError):
                await search(sessions, limit=2, cursor=c, **kw)
        with pytest.raises(ValueError):  # bound to its query
            await search(sessions, limit=2, cursor=first_cursor, q="other", embedding=q)
        with pytest.raises(ValueError):  # bound to its filters
            await search(sessions, limit=2, cursor=first_cursor, variant=VariantFilter(in_stock=True), **kw)
        with pytest.raises(ValueError):  # and to its weights
            await search(sessions, limit=2, cursor=first_cursor, weights=normalize_weights(1, 3), **kw)
        if use_embedding:
            with pytest.raises(ValueError):  # and to the embedding space: a lexical cursor is refused by a hybrid search
                lexical_first = (await search(sessions, limit=2, **{**kw, "embedding": None})).next_cursor
                await search(sessions, limit=2, cursor=lexical_first, **kw)

    run_repo(pg_engine_factory, scenario)
