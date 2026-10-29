"""P1-S4b: embedding tables, constraints and HNSW indexes on real PostgreSQL + pgvector."""
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models.relational_model import EMBEDDING_DIMENSIONS, Product, ProductEmbedding, VariantEmbedding
from repositories import products as products_repo
from tests.integration.conftest import alembic_config
from tests.integration.repo_helpers import product_input, run_repo, tx
from tests.integration.test_catalogue_schema import table_names

KEY = {"source_revision": 1, "representation_version": "catalog-text-v1", "representation_hash": "h1", "provider": "fake",
       "model": "fake-sha256-v1", "model_revision": "", "index_version": "idx-1"}


def vec(first: float = 1.0) -> list[float]:
    return [first] + [0.0] * (EMBEDDING_DIMENSIONS - 1)


async def seed(session, slug="classic-pashmina"):
    product = await products_repo.create_product(session, product_input(slug, status="active"))
    return product.id, product.variants[0].id


def test_migration_downgrade_removes_only_embedding_tables_and_reupgrade_restores_them(pg_url, migrated_url, pg_engine_factory):
    config = alembic_config(pg_url)
    assert {"product_embeddings", "variant_embeddings"} <= table_names(pg_url)
    try:
        command.downgrade(config, "0008")
        tables = table_names(pg_url)
        assert not {"product_embeddings", "variant_embeddings"} & tables
        assert {"products", "variants", "staged_products", "enrichment_suggestions", "catalog_attributes", "outbox"} <= tables
        async def extension(sessions):
            async with sessions() as s:
                return (await s.execute(text("select count(*) from pg_extension where extname = 'vector'"))).scalar()
        assert run_repo(pg_engine_factory, extension) == 1            # shared infrastructure stays
        command.upgrade(config, "head")                                 # re-upgrade after a downgrade
        assert {"product_embeddings", "variant_embeddings"} <= table_names(pg_url)
    finally:
        command.upgrade(config, "head")


def test_hnsw_indexes_are_bounded_cosine_and_partial(pg_engine_factory):
    async def scenario(sessions):
        async with sessions() as s:
            return {r.indexname: r.indexdef for r in await s.execute(text(
                "select indexname, indexdef from pg_indexes where tablename in ('product_embeddings','variant_embeddings')"))}
    defs = run_repo(pg_engine_factory, scenario)
    for table in ("product_embeddings", "variant_embeddings"):
        d = defs[f"ix_{table}_embedding_hnsw"]
        assert "USING hnsw" in d and "vector_cosine_ops" in d and "m='16'" in d and "ef_construction='64'" in d
        assert "status = 'succeeded'" in d
        assert f"ix_{table}_product_id" in defs and f"uq_{table}_identity" in defs


def test_nearest_neighbour_query_uses_the_hnsw_index(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            pid, _ = await seed(s)
            for i in range(3):
                s.add(ProductEmbedding(product_id=pid, **{**KEY, "representation_hash": f"h{i}"}, status="succeeded", embedding=vec(i + 1)))
        async with sessions() as s:
            await s.execute(text("set enable_seqscan = off"))
            plan = "\n".join(r[0] for r in await s.execute(text(
                "explain select id from product_embeddings where status = 'succeeded' "
                f"order by embedding <=> '{vec(1.0)}'::vector limit 2")))
            return plan
    assert "ix_product_embeddings_embedding_hnsw" in run_repo(pg_engine_factory, scenario)


def test_constraints_reject_bad_rows(pg_engine_factory):
    async def insert(sessions, model, **over):
        async with tx(sessions) as s:
            pid, vid = await seed(s, f"p-{len(over)}-{id(over)}")
            owner = {"product_id": pid} if model is ProductEmbedding else {"variant_id": vid, "product_id": pid}
            s.add(model(**owner, **{**KEY, **over}))

    bad = [{"status": "applied"}, {"status": "succeeded"},                  # succeeded needs a vector
           {"status": "running"},                                           # running needs a lease
           {"dimensions": 16}, {"distance_metric": "l2"}, {"source_revision": 0},
           {"attempts": 4}, {"embedding": [1.0, 2.0]}]                      # wrong width
    for model in (ProductEmbedding, VariantEmbedding):
        for over in bad:
            with pytest.raises(Exception):
                run_repo(pg_engine_factory, lambda sessions, m=model, o=over: insert(sessions, m, **o))


def test_identity_is_unique_per_owner_and_variant_must_belong_to_its_product(pg_engine_factory):
    async def duplicate(sessions):
        async with tx(sessions) as s:
            pid, vid = await seed(s, "dup")
            s.add(ProductEmbedding(product_id=pid, **KEY))
            s.add(VariantEmbedding(variant_id=vid, product_id=pid, **KEY))
        async with tx(sessions) as s:
            s.add(ProductEmbedding(product_id=pid, **KEY))
    with pytest.raises(IntegrityError):
        run_repo(pg_engine_factory, duplicate)

    async def new_revision_is_a_new_row(sessions):
        async with tx(sessions) as s:
            pid, _ = await seed(s, "revs")
            s.add(ProductEmbedding(product_id=pid, **KEY))
            s.add(ProductEmbedding(product_id=pid, **{**KEY, "source_revision": 2}))
    run_repo(pg_engine_factory, new_revision_is_a_new_row)  # does not raise

    async def foreign_variant(sessions):
        async with tx(sessions) as s:
            _, vid = await seed(s, "first")
            other, _ = await seed(s, "second")
            s.add(VariantEmbedding(variant_id=vid, product_id=other, **KEY))
    with pytest.raises(IntegrityError):
        run_repo(pg_engine_factory, foreign_variant)


def test_embeddings_follow_their_owner_on_delete_and_never_block_catalogue_writes(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            pid, vid = await seed(s)
            s.add(ProductEmbedding(product_id=pid, **KEY))
            s.add(VariantEmbedding(variant_id=vid, product_id=pid, **KEY))
        async with tx(sessions) as s:
            await s.delete(await s.get(Product, pid))
        async with sessions() as s:
            return [(await s.execute(text(f"select count(*) from {t}"))).scalar() for t in ("product_embeddings", "variant_embeddings")]
    assert run_repo(pg_engine_factory, scenario) == [0, 0]
