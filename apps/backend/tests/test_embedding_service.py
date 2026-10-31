"""P1-S4b: container-free guards for the embedding foundation (safe defaults, wiring, isolation, no network)."""
import asyncio
import importlib.util
import re
import socket
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from configuration.config import settings
from models.relational_model import EMBEDDING_DIMENSIONS
from search import embedding_service
from search.providers import FakeEmbeddingProvider, embed_checked
from workers import embedding_jobs
from workers.queues import QUEUES
from workers.settings import EmbeddingWorkerSettings, WorkerSettings

BACKEND = Path(__file__).resolve().parents[1]
EMBEDDING_FILES = [BACKEND / p for p in ("repositories/embeddings.py", "search/embedding_service.py",
                                         "workers/embedding_jobs.py", "scripts/embedding_backfill.py")]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


def run(coro):
    return asyncio.run(coro)


def test_embeddings_are_off_by_default_with_no_provider():
    fields = type(settings).model_fields
    assert fields["embedding_enabled"].default is False and fields["embedding_provider"].default == ""
    assert fields["embedding_dimensions"].default == EMBEDDING_DIMENSIONS
    assert 1 <= fields["embedding_max_attempts"].default <= 5 and fields["embedding_backfill_max_limit"].default <= 1000


def test_migration_and_model_agree_on_width_and_there_is_one_head():
    spec = importlib.util.spec_from_file_location("m0009", BACKEND / "migrations/versions/0009_embeddings_search.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DIMENSIONS == EMBEDDING_DIMENSIONS and module.down_revision == "0008"
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    assert len(ScriptDirectory.from_config(config).get_heads()) == 1   # one linear chain; 0009 is no longer the head (our 0010-0015 follow it)


def test_the_embedding_worker_has_its_own_bounded_queue_and_no_startup_or_cron_work():
    assert EmbeddingWorkerSettings.queue_name == QUEUES["embeddings"] != WorkerSettings.queue_name
    assert EmbeddingWorkerSettings.functions == [embedding_jobs.run_embedding_job]
    assert embedding_jobs.run_embedding_job not in WorkerSettings.functions
    assert not hasattr(EmbeddingWorkerSettings, "cron_jobs")
    assert 1 <= EmbeddingWorkerSettings.max_jobs <= 8 and EmbeddingWorkerSettings.job_timeout <= 300
    assert EmbeddingWorkerSettings.max_tries <= 6


def test_the_job_skips_cleanly_without_postgres_when_disabled_or_without_a_provider(monkeypatch):
    job = embedding_jobs.run_embedding_job
    assert "postgres" in run(job({}, "product", "x"))["skipped"]
    assert "disabled" in run(job({"pg_sessions": object()}, "product", "x"))["skipped"]
    monkeypatch.setattr(settings, "embedding_enabled", True)
    monkeypatch.setattr(settings, "embedding_provider", "")
    assert "not configured" in run(job({"pg_sessions": object()}, "product", "x"))["skipped"]  # fails closed, no fake fallback


def test_enqueue_without_redis_returns_none_instead_of_raising(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "")
    assert run(embedding_jobs.enqueue_embedding("product", "00000000-0000-0000-0000-000000000000")) is None


def test_the_fake_provider_path_needs_no_network():
    provider = FakeEmbeddingProvider(EMBEDDING_DIMENSIONS)
    [vector] = run(embed_checked(provider, ["type: product\nname: x"]))
    assert len(vector) == EMBEDDING_DIMENSIONS
    assert embedding_service.provider_identity(provider) == {"provider": "fake", "model": "fake-sha256-v1", "model_revision": ""}


def test_embedding_code_never_writes_catalogue_staging_or_enrichment_tables():
    write = re.compile(r"\b(update|insert|delete|pg_insert)\(\s*(Product|Variant|Staged\w*|Enrichment\w*|CatalogAttribute|Outbox)\b")
    for path in EMBEDDING_FILES:
        assert not write.search(path.read_text()), path.name
