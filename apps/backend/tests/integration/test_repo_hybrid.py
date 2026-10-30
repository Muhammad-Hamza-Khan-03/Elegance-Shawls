"""Hybrid retrieval on real PostgreSQL + pgvector with deterministic fake vectors (no provider, no network)."""
import pytest

from models.relational_model import ProductEmbedding
from repositories import embeddings as emb
from repositories import products as catalogue
from repositories.hybrid import hybrid_search
from repositories.products import VariantFilter, VariantInput
from semantic.embeddings import EmbeddingConfig, FakeEmbeddingProvider
from semantic.ranking import normalize_weights
from semantic.representation import represent
from tests.integration.repo_helpers import product_input, run_repo, tx
from utils.pagination import encode_cursor

PROVIDER = FakeEmbeddingProvider(EmbeddingConfig("fake", "fake-hash-v1", 64))
TARGET = emb.Target("fake", "fake-hash-v1", "ps-v1")


def v(name, price, stock, color=None):
    return VariantInput(name=name, color=color or name, image_url="https://img.example/v.jpg", price=price, stock=stock)


async def make(sessions, slug, name, variants, embed=True, **over):
    async with tx(sessions) as s:
        p = await catalogue.create_product(s, product_input(slug, name=name, status="active", variants=variants, **over))
        if embed:
            revision, source = await emb.source_for(s, p.id)
            s.add(ProductEmbedding(product_id=p.id, provider="fake", model="fake-hash-v1", dimensions=64,
                                   representation_version="ps-v1", product_revision=revision,
                                   content_hash=represent(source)["fingerprint"],
                                   embedding=list(PROVIDER.embed(represent(source)["text"]))))
    return p.id


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
        await make(sessions, "plain", "Plain", [v("Red", 4000, 3)], embed=False)
        async with tx(sessions) as s:
            await catalogue.archive_product(s, archived)
            await catalogue.set_variant_stock(s, stale, (await catalogue.get_product(s, stale)).variants[0].id, 1)  # revision bump
        everything = await search(sessions, q="shawls", embedder=PROVIDER)
        assert everything.mode == "hybrid"
        assert {p.id for p in everything.items} == {ok, split, pricey}  # archived/stale/unembedded semantic hits are out
        f = VariantFilter(colour="red", max_price=5000, in_stock=True)
        filtered = await search(sessions, q="shawls", embedder=PROVIDER, variant=f)
        assert [p.id for p in filtered.items] == [ok]
        # same filter, lexical-only: identical visibility rules
        lexical = await search(sessions, q="ok", variant=f)
        assert lexical.mode == "lexical" and [p.id for p in lexical.items] == [ok]
        assert (await search(sessions, q="archived")).items == []

    run_repo(pg_engine_factory, scenario)


def test_lexical_fallback_when_semantic_unavailable(pg_engine_factory):
    class Boom:
        config = PROVIDER.config

        def embed(self, text):
            raise RuntimeError("down")

    class WrongDims(Boom):
        def embed(self, text):
            return [1.0, 2.0]

    async def scenario(sessions):
        a = await make(sessions, "a", "Shawls Alpha", [v("Red", 100, 1)])
        await make(sessions, "b", "Other", [v("Red", 100, 1)])
        results = [await search(sessions, q="shawls", embedder=e) for e in (None, Boom(), WrongDims())]
        assert all(r.mode == "lexical" and [p.id for p in r.items] == [a] for r in results)
        assert (await search(sessions, q="shawls", embedder=PROVIDER)).mode == "hybrid"
        assert (await search(sessions, q="  ", embedder=PROVIDER)).mode == "lexical"  # nothing to embed

    run_repo(pg_engine_factory, scenario)


def test_fusion_weights_and_repeatability(pg_engine_factory):
    async def scenario(sessions):
        both = await make(sessions, "both", "Shawls Wrap", [v("Red", 100, 1)])
        lex = await make(sessions, "lex", "Shawls Wrap Two", [v("Red", 100, 1)], embed=False)
        sem = await make(sessions, "sem", "Plain", [v("Red", 100, 1)])
        runs = [[p.id for p in (await search(sessions, q="shawls", embedder=PROVIDER)).items] for _ in range(3)]
        assert runs[0] == runs[1] == runs[2] and runs[0][0] == both and set(runs[0]) == {both, lex, sem}
        lex_only = await search(sessions, q="shawls", embedder=PROVIDER, weights=normalize_weights(1, 0))
        assert [p.id for p in lex_only.items][-1] == sem
        sem_only = await search(sessions, q="shawls", embedder=PROVIDER, weights=normalize_weights(0, 1))
        assert [p.id for p in sem_only.items][-1] == lex

    run_repo(pg_engine_factory, scenario)


@pytest.mark.parametrize("embedder", [None, PROVIDER])
def test_pages_are_stable_complete_and_cursors_strict(pg_engine_factory, embedder):
    async def scenario(sessions):
        for i in range(5):
            await make(sessions, f"s{i}", f"Shawls {i}", [v("Red", 100, 1)], embed=bool(i % 2))
        kw = {"q": "shawls", "embedder": embedder}
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
        bad = [first_cursor[:-1], first_cursor + "x", "garbage", encode_cursor(*(await _key(sessions))),
               ]
        for c in bad:
            with pytest.raises(ValueError):
                await search(sessions, limit=2, cursor=c, **kw)
        with pytest.raises(ValueError):  # bound to its query
            await search(sessions, limit=2, cursor=first_cursor, q="other", embedder=embedder)
        with pytest.raises(ValueError):  # bound to its filters
            await search(sessions, limit=2, cursor=first_cursor, variant=VariantFilter(in_stock=True), **kw)
        with pytest.raises(ValueError):  # and to its weights
            await search(sessions, limit=2, cursor=first_cursor, weights=normalize_weights(1, 3), **kw)

    async def _key(sessions):
        async with sessions() as s:
            p = (await catalogue.list_products(s, public=True, limit=1)).items[0]
        return p.created_at, p.id

    run_repo(pg_engine_factory, scenario)
