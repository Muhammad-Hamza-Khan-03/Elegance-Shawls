"""P1-S4b: embedding service, worker job and backfill on real PostgreSQL with the offline fake provider."""
import asyncio
import uuid

import pytest
from arq import Retry
from sqlalchemy import text, update

from configuration.config import settings
from models.relational_model import EMBEDDING_DIMENSIONS, Product, Variant
from repositories import embeddings as repo
from repositories import products as products_repo
from repositories import staged as staged_repo
from scripts.embedding_backfill import backfill
from search import embedding_service as svc
from search.providers import FakeEmbeddingProvider
from tests.integration.repo_helpers import product_input, run_repo, stage_kwargs, tx
from workers import queues
from workers.embedding_jobs import enqueue_embedding, run_embedding_job

INDEX = "idx-test"
RUN = {"lease_seconds": 60, "backoff_seconds": 0}
ACTIVE = {"representation_version": "catalog-text-v1", "provider": "fake", "model": "fake-sha256-v1", "model_revision": "",
          "index_version": INDEX}


class Hooked(FakeEmbeddingProvider):
    """Fake provider that runs a callback (or raises) while the provider call is in flight."""
    def __init__(self, dimensions=EMBEDDING_DIMENSIONS, hook=None, exc=None, vectors=None):
        super().__init__(dimensions)
        self.hook, self.exc, self.vectors, self.calls = hook, exc, vectors, 0

    async def embed(self, texts):
        self.calls += 1
        if self.hook:
            await self.hook()
        if self.exc:
            raise self.exc
        return self.vectors if self.vectors is not None else await super().embed(texts)


def fake() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(EMBEDDING_DIMENSIONS)


async def make_product(sessions, slug="classic-pashmina", status="active"):
    async with tx(sessions) as s:
        p = await products_repo.create_product(s, product_input(slug, status=status, main_description="Soft wool."))
        return p.id, p.variants[0].id


async def pending(sessions, kind, owner_id, provider=None):
    async with tx(sessions) as s:
        row, created = await svc.ensure_pending(s, kind, owner_id, provider or fake(), index_version=INDEX, max_attempts=3)
        return row, created


async def go(sessions, kind, row_id, provider=None, **over):
    return await svc.process(sessions, provider or fake(), kind, row_id, **{**RUN, **over})


async def fetch(sessions, kind, row_id):
    async with sessions() as s:
        return await repo.get(s, kind, row_id)


async def active(sessions, kind):
    async with sessions() as s:
        return await svc.active_embeddings(s, kind, **ACTIVE)


async def edit(sessions, product_id, **values):
    async with tx(sessions) as s:
        await s.execute(update(Product).where(Product.id == product_id).values(revision=Product.revision + 1, **values))


def test_embeds_a_public_product_and_a_variant_idempotently(pg_engine_factory):
    async def scenario(sessions):
        pid, vid = await make_product(sessions)
        out = {}
        for kind, owner in (("product", pid), ("variant", vid)):
            row, created = await pending(sessions, kind, owner)
            again, created_again = await pending(sessions, kind, owner)
            assert created and not created_again and again.id == row.id
            assert (await go(sessions, kind, row.id))["status"] == "succeeded"
            assert (await go(sessions, kind, row.id))["status"] == "skipped"         # a finished row is never re-claimed
            done = await fetch(sessions, kind, row.id)
            assert done.status == "succeeded" and len(done.embedding) == EMBEDDING_DIMENSIONS and done.attempts == 1
            assert done.lease_owner is None and done.finished_at and done.dimensions == EMBEDDING_DIMENSIONS
            out[kind] = [r.id for r in await active(sessions, kind)] == [row.id]
        return out
    assert run_repo(pg_engine_factory, scenario) == {"product": True, "variant": True}


def test_changed_revision_creates_a_new_version_and_old_vectors_are_kept_but_inactive(pg_engine_factory):
    async def scenario(sessions):
        pid, _ = await make_product(sessions)
        first, _ = await pending(sessions, "product", pid)
        await go(sessions, "product", first.id)
        await edit(sessions, pid, name="Renamed Pashmina")
        second, created = await pending(sessions, "product", pid)
        assert created and second.id != first.id and second.source_revision == first.source_revision + 1
        assert [r.id for r in await active(sessions, "product")] == []               # revision moved on: nothing is active yet
        await go(sessions, "product", second.id)
        assert [r.id for r in await active(sessions, "product")] == [second.id]
        old = await fetch(sessions, "product", first.id)
        return old.embedding is not None and old.status in ("succeeded", "stale")    # retained, never searchable
    assert run_repo(pg_engine_factory, scenario)


def test_same_revision_new_representation_hash_supersedes_the_old_row(pg_engine_factory):
    async def scenario(sessions):
        pid, _ = await make_product(sessions)
        first, _ = await pending(sessions, "product", pid)
        await go(sessions, "product", first.id)
        async with tx(sessions) as s:                                                 # text changed without a revision bump
            await s.execute(update(Product).where(Product.id == pid).values(main_description="Different words."))
        second, created = await pending(sessions, "product", pid)
        await go(sessions, "product", second.id)
        return created, (await fetch(sessions, "product", first.id)).status, [r.id for r in await active(sessions, "product")] == [second.id]
    assert run_repo(pg_engine_factory, scenario) == (True, "stale", True)


def test_content_change_at_the_same_revision_deactivates_the_old_vector_before_the_replacement_completes(pg_engine_factory):
    async def scenario(sessions):
        pid, vid = await make_product(sessions)
        owners = (("product", pid), ("variant", vid))
        old = {}
        for kind, owner in owners:
            old[kind], _ = await pending(sessions, kind, owner)
            await go(sessions, kind, old[kind].id)
            assert [r.id for r in await active(sessions, kind)] == [old[kind].id]
        async with tx(sessions) as s:                                                 # content changes, revision does not
            await s.execute(update(Product).where(Product.id == pid).values(name="Reworded Pashmina", main_description="New text."))
            await s.execute(update(Variant).where(Variant.id == vid).values(color="Crimson"))
        before_ensure = {k: await active(sessions, k) for k, _ in owners}
        new = {k: (await pending(sessions, k, o))[0] for k, o in owners}
        while_pending = {k: await active(sessions, k) for k, _ in owners}             # replacement queued, not complete
        for kind, _ in owners:
            await go(sessions, kind, new[kind].id)
        after = {k: [r.id for r in await active(sessions, k)] for k, _ in owners}
        return before_ensure, while_pending, after == {k: [new[k].id] for k, _ in owners} and all(new[k].id != old[k].id for k, _ in owners)
    assert run_repo(pg_engine_factory, scenario) == ({"product": [], "variant": []}, {"product": [], "variant": []}, True)


def test_a_stale_completion_cannot_publish_a_vector(pg_engine_factory):
    async def scenario(sessions):
        pid, _ = await make_product(sessions)
        row, _ = await pending(sessions, "product", pid)
        provider = Hooked(hook=lambda: edit(sessions, pid, name="Changed While Embedding"))
        result = await go(sessions, "product", row.id, provider)
        done = await fetch(sessions, "product", row.id)
        return result["status"], done.status, done.embedding, await active(sessions, "product")
    status, row_status, vector, searchable = run_repo(pg_engine_factory, scenario)
    assert (status, row_status, vector, searchable) == ("stale", "stale", None, [])


def test_a_worker_that_lost_its_lease_cannot_overwrite_the_new_holder(pg_engine_factory):
    async def scenario(sessions):
        pid, _ = await make_product(sessions)
        row, _ = await pending(sessions, "product", pid)
        winner = Hooked(vectors=[[0.5] * EMBEDDING_DIMENSIONS])

        async def lease_expires_and_another_worker_finishes():
            async with tx(sessions) as s:
                await s.execute(text("update product_embeddings set lease_expires_at = now() - interval '1 minute'"))
            assert (await go(sessions, "product", row.id, winner))["status"] == "succeeded"

        slow = Hooked(hook=lease_expires_and_another_worker_finishes)
        result = await go(sessions, "product", row.id, slow)
        done = await fetch(sessions, "product", row.id)
        return result["status"], done.status, done.embedding[0], done.attempts
    assert run_repo(pg_engine_factory, scenario) == ("lease_lost", "succeeded", pytest.approx(0.5), 2)


def test_archive_unpublish_and_inactive_variant_are_immediately_not_active(pg_engine_factory):
    async def scenario(sessions):
        pid, vid = await make_product(sessions)
        rows = {k: (await pending(sessions, k, o))[0] for k, o in (("product", pid), ("variant", vid))}
        for k, row in rows.items():
            await go(sessions, k, row.id)
        assert len(await active(sessions, "product")) == len(await active(sessions, "variant")) == 1
        async with tx(sessions) as s:                                                 # variant hidden, same product revision
            await s.execute(update(Variant).where(Variant.id == vid).values(is_active=False))
        after_variant = len(await active(sessions, "variant"))
        async with tx(sessions) as s:
            await products_repo.archive_product(s, pid)
        return after_variant, len(await active(sessions, "product")), len(await active(sessions, "variant"))
    assert run_repo(pg_engine_factory, scenario) == (0, 0, 0)


def test_non_public_owners_get_no_row_and_a_row_going_non_public_ends_stale(pg_engine_factory):
    async def scenario(sessions):
        draft, _ = await make_product(sessions, "draft-one", status="draft")
        assert await pending(sessions, "product", draft) == (None, False)
        pid, _ = await make_product(sessions)
        row, _ = await pending(sessions, "product", pid)
        async with tx(sessions) as s:
            await products_repo.archive_product(s, pid)
        return (await go(sessions, "product", row.id))["status"], (await fetch(sessions, "product", row.id)).embedding
    assert run_repo(pg_engine_factory, scenario) == ("stale", None)


@pytest.mark.parametrize("provider, retryable", [
    (Hooked(dimensions=16), False),                                                   # wrong dimensions
    (Hooked(vectors=[[float("nan")] * EMBEDDING_DIMENSIONS]), False),
    (Hooked(vectors=[[float("inf")] * EMBEDDING_DIMENSIONS]), False),
    (Hooked(vectors=[[0.1] * 5]), False),                                             # wrong vector length
    (Hooked(exc=ValueError("boom")), False),                                          # unknown failures fail closed
])
def test_invalid_provider_output_fails_without_a_vector_and_without_retry(pg_engine_factory, provider, retryable):
    async def scenario(sessions):
        pid, _ = await make_product(sessions)
        row, _ = await pending(sessions, "product", pid, provider)
        result = await go(sessions, "product", row.id, provider)
        done = await fetch(sessions, "product", row.id)
        return result["status"], done.status, done.embedding, done.last_error_retryable, done.attempts, await active(sessions, "product")
    assert run_repo(pg_engine_factory, scenario) == ("failed", "failed", None, retryable, 1, [])


def test_retryable_failures_back_off_then_end_in_a_terminal_failed_state(pg_engine_factory):
    async def scenario(sessions):
        pid, _ = await make_product(sessions)
        provider = Hooked(exc=TimeoutError())
        row, _ = await pending(sessions, "product", pid, provider)
        seen = [(await go(sessions, "product", row.id, provider, backoff_seconds=300))["status"]]
        assert (await fetch(sessions, "product", row.id)).status == "queued"
        seen.append((await go(sessions, "product", row.id, provider))["status"])      # backoff not elapsed: not claimable
        async with tx(sessions) as s:
            await s.execute(text("update product_embeddings set available_at = now()"))
        seen += [(await go(sessions, "product", row.id, provider))["status"] for _ in range(2)]
        async with tx(sessions) as s:
            await s.execute(text("update product_embeddings set available_at = now()"))
        seen.append((await go(sessions, "product", row.id, provider))["status"])      # attempts exhausted: never claimed again
        done = await fetch(sessions, "product", row.id)
        return seen, done.status, done.attempts, done.last_error_retryable, provider.calls
    assert run_repo(pg_engine_factory, scenario) == (["retry", "skipped", "retry", "failed", "skipped"], "failed", 3, True, 3)


def test_lease_recovery_and_exhausted_abandoned_lease(pg_engine_factory):
    async def scenario(sessions):
        a, _ = await make_product(sessions, "alpha")
        b, _ = await make_product(sessions, "beta")
        ra, _ = await pending(sessions, "product", a)
        rb, _ = await pending(sessions, "product", b)
        async with tx(sessions) as s:                                                 # both look abandoned or live
            await s.execute(text("update product_embeddings set status='running', attempts=1, lease_owner='dead', "
                                 "lease_expires_at = now() + interval '1 hour' where id = :i"), {"i": ra.id})
            await s.execute(text("update product_embeddings set status='running', attempts=3, lease_owner='dead', "
                                 "lease_expires_at = now() - interval '1 minute' where id = :i"), {"i": rb.id})
        live = (await go(sessions, "product", ra.id))["status"]                      # lease still valid: left alone
        exhausted = (await go(sessions, "product", rb.id))["status"]
        async with tx(sessions) as s:
            await s.execute(text("update product_embeddings set lease_expires_at = now() - interval '1 minute' where id = :i"), {"i": ra.id})
        recovered = (await go(sessions, "product", ra.id))["status"]
        return live, exhausted, (await fetch(sessions, "product", rb.id)).status, recovered, (await fetch(sessions, "product", ra.id)).attempts
    assert run_repo(pg_engine_factory, scenario) == ("skipped", "skipped", "failed", "succeeded", 2)


@pytest.fixture
def index_version(monkeypatch):
    monkeypatch.setattr(settings, "embedding_index_version", INDEX)


def snapshot(sessions):
    async def read():
        async with sessions() as s:
            return {t: [tuple(r) for r in await s.execute(text(f"select to_jsonb(x)::text from {t} x order by 1"))]
                    for t in ("products", "variants", "staged_products", "staged_product_audit", "enrichment_suggestions",
                              "catalog_attributes", "outbox")}
    return read()


def test_a_full_embed_cycle_leaves_catalogue_staging_and_enrichment_state_unchanged(pg_engine_factory, index_version):
    async def scenario(sessions):
        async with tx(sessions) as s:
            staged = (await staged_repo.stage_product(s, **stage_kwargs(1)))[0]
            await staged_repo.approve(s, staged.id, price=4500, stock=3)
            await staged_repo.publish(s, staged.id, actor="admin")
        before = await snapshot(sessions)
        summary = [await backfill(sessions, fake(), kind=k, limit=10, dry_run=False) for k in ("product", "variant")]
        assert summary[0]["succeeded"] == 1 and summary[1]["succeeded"] == 2
        return before == await snapshot(sessions)
    assert run_repo(pg_engine_factory, scenario)


def test_backfill_dry_run_limit_resume_and_idempotency(pg_engine_factory, index_version):
    async def scenario(sessions):
        ids = sorted([(await make_product(sessions, f"shawl-{i}"))[0] for i in range(3)])
        dry = await backfill(sessions, fake(), kind="product", limit=2, dry_run=True)
        async with sessions() as s:
            assert (await s.execute(text("select count(*) from product_embeddings"))).scalar() == 0
        first = await backfill(sessions, fake(), kind="product", limit=2, dry_run=False)
        resumed = await backfill(sessions, fake(), kind="product", limit=2, dry_run=False, after=uuid.UUID(first["last_id"]))
        rerun = await backfill(sessions, fake(), kind="product", limit=5, dry_run=False)
        async with sessions() as s:
            rows = (await s.execute(text("select count(*) from product_embeddings"))).scalar()
        return ids, dry, first, resumed, rerun, rows
    ids, dry, first, resumed, rerun, rows = run_repo(pg_engine_factory, scenario)
    assert (dry["examined"], dry["would_create"], dry["last_id"]) == (2, 2, str(ids[1]))
    assert (first["examined"], first["created"], first["succeeded"], first["last_id"]) == (2, 2, 2, str(ids[1]))
    assert (resumed["examined"], resumed["created"], resumed["succeeded"], resumed["last_id"]) == (1, 1, 1, str(ids[2]))
    assert (rerun["examined"], rerun["already_succeeded"], rerun.get("created", 0)) == (3, 3, 0) and rows == 3


def test_backfill_enforces_the_limit_bounds_and_skips_drafts(pg_engine_factory, index_version):
    async def scenario(sessions):
        await make_product(sessions, "hidden", status="draft")
        for bad in (0, settings.embedding_backfill_max_limit + 1):
            with pytest.raises(ValueError):
                await backfill(sessions, fake(), kind="product", limit=bad, dry_run=True)
        return await backfill(sessions, fake(), kind="product", limit=5, dry_run=False)
    assert run_repo(pg_engine_factory, scenario)["examined"] == 0


def test_worker_job_embeds_through_the_job_entry_point(pg_engine_factory, monkeypatch, index_version):
    monkeypatch.setattr(settings, "embedding_enabled", True)

    async def scenario(sessions):
        pid, _ = await make_product(sessions)
        row, _ = await pending(sessions, "product", pid)
        ctx = {"pg_sessions": sessions, "embedding_provider": fake()}
        ok = await run_embedding_job(ctx, "product", str(row.id))
        retry_provider = Hooked(exc=TimeoutError())
        pid2, _ = await make_product(sessions, "second")
        row2, _ = await pending(sessions, "product", pid2, retry_provider)
        monkeypatch.setattr(settings, "embedding_backoff_seconds", 7.0)
        with pytest.raises(Retry) as retry:
            await run_embedding_job({"pg_sessions": sessions, "embedding_provider": retry_provider}, "product", str(row2.id))
        return ok, retry.value.defer_score
    ok, defer_score = run_repo(pg_engine_factory, scenario)
    assert ok == {"status": "succeeded"} and defer_score == 7000                          # arq stores the delay in ms


def test_redis_unavailable_never_blocks_and_leaves_the_row_queued(pg_engine_factory, monkeypatch, index_version):
    async def scenario(sessions):
        pid, _ = await make_product(sessions)
        row, _ = await pending(sessions, "product", pid)
        monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1")             # nothing listens there
        queues._pool = None
        assert await enqueue_embedding("product", row.id) is None
        monkeypatch.setattr(settings, "redis_url", "")
        assert await enqueue_embedding("product", row.id) is None
        return (await fetch(sessions, "product", row.id)).status
    assert run_repo(pg_engine_factory, scenario) == "queued"


def test_job_enqueue_uses_a_deterministic_id_on_its_own_queue(redis_url, monkeypatch):
    from redis.asyncio import Redis

    monkeypatch.setattr(settings, "redis_url", redis_url)
    row_id = uuid.uuid4()

    async def work():
        await Redis.from_url(redis_url).flushdb()
        queues._pool = None
        try:
            first = await enqueue_embedding("product", row_id)
            second = await enqueue_embedding("product", row_id)
            return first, second, await queues._pool.zcard(queues.QUEUES["embeddings"]), await queues._pool.zcard(queues.QUEUES["default"])
        finally:
            await queues.close_queue_pool()
    first, second, on_embeddings, on_default = asyncio.run(work())
    assert first == f"embed:product:{row_id}" and second is None and (on_embeddings, on_default) == (1, 0)
