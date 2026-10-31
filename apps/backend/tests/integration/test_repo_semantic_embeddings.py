import uuid

from models.relational_model import SemanticEmbeddingJob, SemanticEmbedding
from repositories import semantic_embeddings as repo
from repositories import products as catalogue
from semantic.representation import represent
from tests.integration.repo_helpers import product_input, run_repo, tx


TARGET = repo.Target(provider="fake", model="fake-hash-v1", representation_version="ps-v1")


def test_same_revision_stale_embedding_is_excluded_until_replacement_succeeds(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as session:
            product = await catalogue.create_product(session, product_input(status="active", name="Original Shawl"))
            source = await repo.source_for(session, product.id)
            assert source is not None
            current_hash = represent(source[1])["fingerprint"]
            session.add(SemanticEmbedding(
                product_id=product.id, provider=TARGET.provider, model=TARGET.model,
                dimensions=3, representation_version=TARGET.representation_version,
                content_hash="0" * 64, product_revision=source[0], embedding=[0.0, 0.0, 0.0],
            ))
            session.add(SemanticEmbeddingJob(
                product_id=product.id, provider=TARGET.provider, model=TARGET.model,
                representation_version=TARGET.representation_version, status="queued",
            ))

        async with sessions() as session:
            assert await repo.servable_product_ids(session, TARGET, limit=10) == []

        async with tx(sessions) as session:
            claimed = await repo.claim_next(session, "worker-1", TARGET)
        assert claimed is not None
        job_id, product_id = claimed

        async with tx(sessions) as session:
            outcome = await repo.finish_job(
                session, job_id, "worker-1", TARGET, product_id,
                revision=source[0], fingerprint=current_hash, vector=[1.0, 2.0, 3.0],
            )
        assert outcome == "embedded"

        async with sessions() as session:
            return await repo.servable_product_ids(session, TARGET, limit=10), product.id

    servable, product_id = run_repo(pg_engine_factory, scenario)
    assert servable == [product_id]
    assert isinstance(product_id, uuid.UUID)
