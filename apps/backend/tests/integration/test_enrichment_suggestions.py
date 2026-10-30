"""P1-S3: enrichment suggestions on real PostgreSQL and Redis (fake provider, zero provider network)."""
import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest
from alembic import command
from sqlalchemy import text

from configuration.config import settings
from enrichment import service
from enrichment.contract import FIELDS, FREE_TEXT, allowed_values
from llm.fake import ProviderReply
from llm.gateway import BudgetTracker
from repositories import enrichment as repo
from repositories import staged as staged_repo
from routes import enrichment_routes
from routes.enrichment_routes import router as enrichment_router
from tests.integration.api_support import ADMIN_KEY, H, ApiEnv
from tests.integration.conftest import alembic_config
from tests.integration.repo_helpers import run_repo, tx
from tests.integration.test_catalogue_schema import table_names
from workers.queues import QueueUnavailable

PRODUCT = {
    "name": "Pearl Cashmere Shawl", "slug": "pearl-cashmere-shawl", "cover_image_url": "https://shop.example/a.jpg",
    "images": ["https://shop.example/a.jpg"], "main_description": "Soft cashmere shawl.", "category": "shawls",
    "material": "Cashmere", "sizing": None, "weight": None,
    "variants": [{"name": "Pearl", "color": "Cream", "size": "Free Size", "image_url": "https://shop.example/a.jpg", "stock": 0}],
}
STATE_TABLES = ("products", "variants", "catalog_attributes", "staged_product_audit", "outbox")


def good_reply() -> str:
    data = {f: {"value": sorted(allowed_values(f))[0], "reason": None} for f in FIELDS if f not in FREE_TEXT}
    data.update({f: {"value": "A soft shawl.", "reason": None} for f in FREE_TEXT})
    return json.dumps(data)


class Script:
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    async def __call__(self, model, messages, timeout):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            await outcome()
            outcome = good_reply()
        return ProviderReply(outcome, cost_usd=0.001)


async def no_sleep(seconds):
    return None


class Env(ApiEnv):
    def __init__(self, url, monkeypatch):
        super().__init__(url, monkeypatch)
        self.app.include_router(enrichment_router)
        self.queued: list[tuple] = []
        monkeypatch.setattr(settings, "enrichment_model", "fake/model")

        async def fake_enqueue(function, *args, **kwargs):
            self.queued.append((function, args))
            return "job-1"

        monkeypatch.setattr(enrichment_routes, "enqueue", fake_enqueue)
        self.monkeypatch = monkeypatch

    def stage(self, slug="pearl-cashmere-shawl", pid="1001"):
        async def work(sessions):
            async with sessions() as session, session.begin():
                row, _ = await staged_repo.stage_product(
                    session, source_id="primary", source_name="Shop", source_url=f"https://shop.example/products/{slug}",
                    source_product_id=pid, source_content_hash="h", fetched_at=datetime.now(timezone.utc),
                    ingestion_job_id=None, source_price=189.0, source_currency="AUD",
                    product={**PRODUCT, "slug": slug}, source_attributes={}, missing_fields=["price", "stock"])
                return str(row.id)

        return self.run(work)

    def url_for(self, sid, suffix=""):
        return f"/products/admin/ingestion/staged/{sid}/enrichment{suffix}"

    def request(self, sid):
        return self.client.post(self.url_for(sid), headers=H)

    def process(self, suggestion_id, script, budget=None):
        async def work(sessions):
            return await service.process(sessions, uuid.UUID(suggestion_id), complete=script,
                                         budget=budget or BudgetTracker(1.0, 10.0, 0.8), sleep=no_sleep)

        return self.run(work)

    def snapshot(self):
        counts = {t: self.sql(f"select count(*) from {t}")[0][0] for t in STATE_TABLES}
        staged = self.sql("select status, product::text, approved_price, product_id, updated_at from staged_products order by id")
        return counts, staged


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    return Env(migrated_url, monkeypatch)


def test_routes_require_admin_auth_and_have_no_apply_route(env):
    sid = str(uuid.uuid4())
    for method, suffix in (("post", ""), ("get", ""), ("post", f"/{uuid.uuid4()}/cancel")):
        assert getattr(env.client, method)(env.url_for(sid, suffix)).status_code in (401, 403)
        assert getattr(env.client, method)(env.url_for(sid, suffix), headers={"X-Admin-Key": "wrong"}).status_code in (401, 403)
    assert {(r.path.rsplit("enrichment", 1)[1], tuple(sorted(r.methods))) for r in enrichment_router.routes} == {
        ("", ("POST",)), ("", ("GET",)), ("/{suggestion_id}/cancel", ("POST",))}
    assert env.client.post(env.url_for(sid, "/apply"), headers=H).status_code in (404, 405)


def test_request_creates_a_queued_suggestion_with_full_provenance_and_is_idempotent(env):
    sid = env.stage()
    first = env.request(sid)
    assert first.status_code == 202
    body = first.json()
    assert body["status"] == "queued" and body["authoritative"] is False and body["suggestions"] is None
    assert body["staged_product_id"] == sid and body["attempts"] == 0
    assert (body["provider"], body["model"], body["prompt_version"], body["vocabulary_version"]) == (
        "fake", "fake/model", "enrich-v1", "enrichment-vocab-1")
    assert len(body["input_content_hash"]) == 64
    again = env.request(sid)
    assert again.status_code == 202 and again.json()["id"] == body["id"]
    assert env.queued == [("run_enrichment_job", (body["id"],))]            # one job per staged product
    assert env.sql("select count(*) from enrichment_suggestions")[0][0] == 1
    assert env.client.get(env.url_for(sid), headers=H).json()["id"] == body["id"]


def test_request_input_validation(env):
    assert env.client.post(env.url_for("not-a-uuid"), headers=H).status_code == 400
    assert env.request(str(uuid.uuid4())).status_code == 404
    assert env.client.get(env.url_for(env.stage()), headers=H).status_code == 404       # nothing requested yet
    env.monkeypatch.setattr(settings, "enrichment_model", "")
    assert env.request(env.stage("other", "2")).status_code == 503


def test_only_an_id_is_accepted_nothing_in_a_body_reaches_the_provider_input(env):
    sid = env.stage()
    assert env.client.post(env.url_for(sid), headers=H, json={"name": "Injected", "price": 1}).status_code == 202
    assert "Injected" not in env.sql("select input_content_hash from enrichment_suggestions")[0][0]


def test_rejected_and_archived_staged_products_are_refused(env):
    sid = env.stage()
    base = f"/products/admin/ingestion/staged/{sid}"
    assert env.client.post(f"{base}/reject", headers=H, json={"reason": "no good"}).status_code == 200
    assert env.request(sid).status_code == 409
    assert env.client.post(f"{base}/archive", headers=H).status_code == 200
    assert env.request(sid).status_code == 409
    assert env.sql("select count(*) from enrichment_suggestions")[0][0] == 0


def test_worker_success_persists_suggestions_and_changes_nothing_else(env):
    sid = env.stage()
    before = env.snapshot()
    body = env.request(sid).json()
    assert env.process(body["id"], Script(good_reply())) == "succeeded"
    done = env.client.get(env.url_for(sid), headers=H).json()
    assert done["status"] == "succeeded" and done["attempts"] == 1 and done["validation_errors"] == []
    assert set(done["suggestions"]) == set(FIELDS) and done["started_at"] and done["finished_at"]
    assert all(v["source"] == "visual_suggestion" for v in done["suggestions"].values())
    assert done["reviewed_by"] is None and done["reviewed_at"] is None
    assert env.snapshot() == before                                  # no product, variant, attribute, outbox or state change
    assert env.sql("select status from staged_products")[0][0] == "pending_review"


def test_invalid_output_is_stored_as_validation_errors_not_suggestions(env):
    body = env.request(env.stage()).json()
    bad = json.loads(good_reply())
    bad["fabric"] = {"value": "silk", "reason": None}
    script = Script(json.dumps(bad), good_reply())
    assert env.process(body["id"], script) == "failed"
    row = env.client.get(env.url_for(body["staged_product_id"]), headers=H).json()
    assert row["suggestions"] is None and row["validation_errors"] and row["last_error"] == "schema_invalid"
    assert script.calls == 1                                         # schema errors never retry


def test_transient_failure_retries_once_then_succeeds_and_permanent_does_not_retry(env):
    first = env.request(env.stage()).json()
    script = Script(ConnectionError("x"), good_reply())
    assert env.process(first["id"], script) == "succeeded" and script.calls == 2
    assert env.client.get(env.url_for(first["staged_product_id"]), headers=H).json()["attempts"] == 2

    second = env.request(env.stage("s2", "2")).json()
    script = Script(ConnectionError("a"), ConnectionError("b"), good_reply())
    assert env.process(second["id"], script) == "failed" and script.calls == 2
    row = env.client.get(env.url_for(second["staged_product_id"]), headers=H).json()
    assert (row["attempts"], row["last_error"]) == (2, "ConnectionError")

    third = env.request(env.stage("s3", "3")).json()
    script = Script(service.ProviderError("groq returned HTTP 401"), good_reply())
    assert env.process(third["id"], script) == "failed" and script.calls == 1


def test_cancel_queued_blocks_the_worker_and_finished_cannot_be_cancelled(env):
    body = env.request(env.stage()).json()
    url = env.url_for(body["staged_product_id"], f"/{body['id']}/cancel")
    cancelled = env.client.post(url, headers=H)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    script = Script(good_reply())
    assert env.process(body["id"], script) == "skipped" and script.calls == 0
    assert env.client.post(url, headers=H).status_code == 409
    other = env.request(env.stage("o", "9")).json()
    assert env.client.post(env.url_for(body["staged_product_id"], f"/{other['id']}/cancel"), headers=H).status_code == 409  # wrong staged id


def test_cancel_while_running_wins_over_the_worker_result(env):
    body = env.request(env.stage()).json()

    async def cancel_during_call():
        engine_url = env.url
        from database.pg import make_engine
        engine = make_engine(engine_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("update enrichment_suggestions set status='cancelled', finished_at=now() where status='running'"))
        finally:
            await engine.dispose()

    assert env.process(body["id"], Script(cancel_during_call)) == "cancelled"
    row = env.client.get(env.url_for(body["staged_product_id"]), headers=H).json()
    assert row["status"] == "cancelled" and row["suggestions"] is None


def test_changed_draft_after_queueing_fails_instead_of_attaching_stale_provenance(env):
    body = env.request(env.stage()).json()
    env.sql("update staged_products set product = jsonb_set(product, '{name}', '\"Renamed\"')")
    script = Script(good_reply())
    assert env.process(body["id"], script) == "failed" and script.calls == 0
    assert env.client.get(env.url_for(body["staged_product_id"]), headers=H).json()["last_error"] == "input_changed"


def test_staged_product_rejected_before_the_worker_runs_is_cancelled(env):
    body = env.request(env.stage()).json()
    env.client.post(f"/products/admin/ingestion/staged/{body['staged_product_id']}/reject", headers=H, json={"reason": "no good"})
    script = Script(good_reply())
    assert env.process(body["id"], script) == "cancelled" and script.calls == 0


def test_queue_failure_marks_the_suggestion_failed_and_returns_503(env):
    async def down(*a, **k):
        raise QueueUnavailable("Redis is unavailable")

    env.monkeypatch.setattr(enrichment_routes, "enqueue", down)
    sid = env.stage()
    assert env.request(sid).status_code == 503
    row = env.client.get(env.url_for(sid), headers=H).json()
    assert (row["status"], row["last_error"]) == ("failed", "queue_unavailable")


def test_a_different_model_is_new_work_only_when_nothing_is_active(env):
    sid = env.stage()
    first = env.request(sid).json()
    env.monkeypatch.setattr(settings, "enrichment_model", "fake/other")
    assert env.request(sid).json()["id"] == first["id"]               # still active: one job per staged product
    env.process(first["id"], Script(good_reply()))
    second = env.request(sid).json()
    assert second["id"] != first["id"] and second["model"] == "fake/other"
    assert env.request(sid).json()["id"] == second["id"]


def test_concurrent_requests_create_one_row_and_concurrent_workers_call_the_provider_once(env):
    sid = env.stage()

    async def create_many(sessions):
        async def one():
            async with sessions() as session, session.begin():
                row, created = await repo.create(session, staged_id=uuid.UUID(sid), input_hash="h" * 64, prompt_version="enrich-v1",
                                                 model="fake/model", vocabulary_version="v", provider="fake", trace_id=None)
                return row.id, created
        return await asyncio.gather(*[one() for _ in range(8)])

    results = env.run(create_many)
    assert len({r[0] for r in results}) == 1 and sum(r[1] for r in results) == 1
    env.sql("delete from enrichment_suggestions")

    body = env.request(sid).json()
    script = Script(good_reply(), good_reply())

    async def race(sessions):
        return await asyncio.gather(*[service.process(sessions, uuid.UUID(body["id"]), complete=script,
                                                      budget=BudgetTracker(1.0, 10.0, 0.8), sleep=no_sleep) for _ in range(4)])

    outcomes = env.run(race)
    assert script.calls == 1 and sorted(outcomes).count("skipped") == 3 and "succeeded" in outcomes


def test_database_enforces_bounds_and_state(env):
    sid = env.stage()
    body = env.request(sid).json()
    with pytest.raises(Exception):
        env.sql("update enrichment_suggestions set attempts = 3")
    with pytest.raises(Exception):
        env.sql("update enrichment_suggestions set status = 'applied'")
    with pytest.raises(Exception):                                     # unique idempotency key
        env.sql("insert into enrichment_suggestions (staged_product_id, input_content_hash, prompt_version, model, vocabulary_version, provider, status) "
                "select staged_product_id, input_content_hash, prompt_version, model, vocabulary_version, provider, 'failed' from enrichment_suggestions")
    assert body["id"]


def test_migration_downgrade_removes_only_this_table_and_upgrade_restores_it(pg_url, migrated_url, pg_engine_factory):
    config = alembic_config(pg_url)
    assert "enrichment_suggestions" in table_names(pg_url)
    try:
        command.downgrade(config, "0007")
        tables = table_names(pg_url)
        assert "enrichment_suggestions" not in tables and {"catalog_attributes", "staged_products", "products"} <= tables
    finally:
        command.upgrade(config, "head")
    assert "enrichment_suggestions" in table_names(pg_url)


def test_redis_backed_budget_is_shared_with_the_enrichment_call(env, redis_url):
    import redis.asyncio as aioredis

    sid = env.stage()

    async def work(sessions):
        client = aioredis.from_url(redis_url)
        try:
            budget = BudgetTracker(1.0, 10.0, 0.8, redis=client)
            body = await _request_via_repo(sessions, sid)
            status = await service.process(sessions, body, complete=Script(good_reply()), budget=budget, sleep=no_sleep)
            keys = await client.keys("llm:spend:*")
            return status, len(keys)
        finally:
            await client.aclose()

    status, keys = env.run(work)
    assert status == "succeeded" and keys == 2


async def _request_via_repo(sessions, sid):
    async with tx(sessions) as session:
        staged = await staged_repo.get_staged(session, uuid.UUID(sid))
        _, digest = service.prepare(staged.product)
        row, _ = await repo.create(session, staged_id=staged.id, input_hash=digest, prompt_version="enrich-v1", model="fake/model",
                                   vocabulary_version="enrichment-vocab-1", provider="fake", trace_id=None)
        return row.id
