"""Container-free M2-S2 checks: runner behaviour over a faked repository, migration SQL, worker wiring, scope guards."""
import ast
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from repositories import embeddings as repo
from semantic import backfill, embeddings as emb
from workers import jobs
from workers.settings import WorkerSettings

BACKEND = Path(__file__).resolve().parents[1]
ENV = {"SEMANTIC_EMBEDDING_PROVIDER": "fake", "SEMANTIC_EMBEDDING_MODEL": "fake-hash-v1", "SEMANTIC_EMBEDDING_DIMENSIONS": "64"}


class Sessions:
    """Stands in for async_sessionmaker: the faked repository never touches the session."""
    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def begin(self):
        return self


class CountingProvider(emb.FakeEmbeddingProvider):
    def __init__(self, fail=None, vector=None):
        super().__init__(emb.load_config(ENV, allow_test_providers=True))
        self.calls, self.fail, self.vector = 0, fail, vector

    def embed(self, text):
        self.calls += 1
        if self.fail:
            raise self.fail
        return self.vector if self.vector is not None else super().embed(text)


def fake_repo(monkeypatch, *, queue, source, stored=None):
    """queue: list of (job_id, product_id); records finish/fail calls."""
    log = SimpleNamespace(finished=[], failed=[], enqueue_args=None)

    async def recover(s, now=None): return 0
    async def purge(s, n): return 0
    async def enqueue(s, target, after, n, now=None):
        log.enqueue_args = (after, n)
        return len(queue), None
    async def claim(s, worker, target, now=None): return queue.pop(0) if queue else None
    async def source_for(s, pid): return source
    async def stored_hash(s, pid, target): return stored
    async def finish(s, jid, worker, target, pid, **kw):
        log.finished.append(kw)
        return "embedded" if kw["vector"] is not None else "fresh"
    async def fail(s, jid, worker, error, *, retryable, now=None):
        log.failed.append((error, retryable))
        return "retrying" if retryable else "failed"

    for name, fn in dict(recover_expired_leases=recover, purge_inactive=purge, enqueue_stale=enqueue, claim_next=claim,
                         source_for=source_for, stored_hash=stored_hash, finish_job=finish, fail_job=fail).items():
        monkeypatch.setattr(repo, name, fn)
    return log


SOURCE = (3, {"name": "Wool Shawl", "category": "shawls", "variants": [{"name": "Grey", "color": "Grey"}]})


async def run(provider, **kw):
    return await backfill.run_backfill(Sessions(), provider, worker_id="w", **kw)


@pytest.mark.asyncio
async def test_missing_embedding_is_embedded_once_with_hash_and_revision(monkeypatch):
    log = fake_repo(monkeypatch, queue=[("j", "p")], source=SOURCE)
    provider = CountingProvider()
    out = await run(provider)
    assert out["embedded"] == 1 and out["queued"] == 1 and provider.calls == 1
    kw = log.finished[0]
    assert kw["revision"] == 3 and len(kw["fingerprint"]) == 64 and len(kw["vector"]) == 64


@pytest.mark.asyncio
async def test_current_hash_does_no_provider_work(monkeypatch):
    from semantic.representation import represent
    log = fake_repo(monkeypatch, queue=[("j", "p")], source=SOURCE, stored=represent(SOURCE[1])["fingerprint"])
    provider = CountingProvider()
    out = await run(provider)
    assert out["fresh"] == 1 and provider.calls == 0 and log.finished[0]["vector"] is None


@pytest.mark.asyncio
async def test_changed_text_with_same_revision_is_stale(monkeypatch):
    log = fake_repo(monkeypatch, queue=[("j", "p")], source=SOURCE, stored="0" * 64)
    provider = CountingProvider()
    await run(provider)
    assert provider.calls == 1 and log.finished[0]["vector"] is not None


@pytest.mark.asyncio
async def test_non_public_product_is_finished_without_a_provider_call(monkeypatch):
    log = fake_repo(monkeypatch, queue=[("j", "p")], source=None)
    provider = CountingProvider()
    await run(provider)
    assert provider.calls == 0 and log.finished[0]["revision"] is None and log.finished[0]["vector"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,retryable", [
    (lambda: CountingProvider(fail=TimeoutError("slow")), True),
    (lambda: CountingProvider(vector=[0.0] * 3), False),               # wrong dimension: deterministic
    (lambda: CountingProvider(vector=[float("nan")] * 64), False),
])
async def test_failures_are_classified_for_retry(monkeypatch, provider, retryable):
    log = fake_repo(monkeypatch, queue=[("j", "p")], source=SOURCE)
    out = await run(provider())
    assert [r for _, r in log.failed] == [retryable] and log.finished == []
    assert out["retrying" if retryable else "failed"] == 1


@pytest.mark.asyncio
async def test_unrepresentable_product_fails_without_retry(monkeypatch):
    log = fake_repo(monkeypatch, queue=[("j", "p")], source=(1, {"name": ""}))
    await run(CountingProvider())
    assert [r for _, r in log.failed] == [False]


@pytest.mark.asyncio
async def test_run_is_bounded_and_clamps_the_limit(monkeypatch):
    log = fake_repo(monkeypatch, queue=[(str(i), "p") for i in range(10)], source=SOURCE)
    out = await run(CountingProvider(), limit=3)
    assert out["embedded"] == 3 and len(log.finished) == 3
    await run(CountingProvider(), limit=10**6)
    assert log.enqueue_args[1] == backfill.MAX_BATCH


def test_default_worker_job_is_inert_without_an_injected_provider():
    import asyncio
    assert asyncio.run(jobs.embedding_backfill_job({})) == {"skipped": "embeddings are not configured"}
    assert jobs.embedding_backfill_job in WorkerSettings.functions
    assert all("embedding" not in getattr(c.name, "__name__", str(c.name)) for c in WorkerSettings.cron_jobs)  # never scheduled


def alembic_sql(*args):
    return subprocess.run([sys.executable, "-m", "alembic", *args, "--sql"], cwd=BACKEND, capture_output=True, text=True,
                          env={"DATABASE_URL": "postgresql+asyncpg://u:p@localhost/x", "PATH": ""}, check=True).stdout


def test_migration_0009_is_additive_and_its_downgrade_reverses_every_object():
    up, down = alembic_sql("upgrade", "0008:0009"), alembic_sql("downgrade", "0009:0008")
    created = {w.rstrip("(") for l in up.splitlines() if l.startswith("CREATE TABLE") for w in [l.split()[2]]}
    assert created == {"product_embeddings", "embedding_jobs"}
    assert "ALTER TABLE" not in up and "DROP" not in up                      # nothing existing is touched
    dropped = {l.split()[2].rstrip(";") for l in down.splitlines() if l.startswith("DROP TABLE")}
    assert dropped == created and "DROP INDEX" not in down                   # indexes go with their tables
    assert "vector_dims(embedding) = dimensions" in up


def test_semantic_code_has_no_route_provider_or_request_path_backfill():
    routes = "".join(p.read_text() for p in (BACKEND / "routes").glob("*.py")) + (BACKEND / "main.py").read_text()
    assert "semantic" not in routes and "embeddings" not in routes
    for path in (BACKEND / "semantic").glob("*.py"):
        imported = {n.module.split(".")[0] for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.ImportFrom) and n.module}
        assert not imported & {"httpx", "llm", "routes"}, path.name
