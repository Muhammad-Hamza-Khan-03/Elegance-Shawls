"""Bounded one-shot refresh: ``python -m ingestion.worker --once``.

Discovers product URLs from each enabled, authorized source's sitemap, queues idempotent jobs
for new or changed products, processes that finite batch and exits. It only ever writes staged
products and ingestion jobs in a staging database; it never approves, publishes, archives or
deletes anything, and products that vanish from a sitemap are reported only.
"""
import asyncio
import json
import logging
import os
import re
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone

from configuration.config import settings
from ingestion.normalize import source_url_for_path
from ingestion.safe_fetch import SafeFetcher, SourcePolicy
from ingestion.sitemap import Discovery, DiscoveryError, canonical_product_path, discover_products
from ingestion.staging_guard import STAGING_NAME, StagingGuardError, assert_staging  # noqa: F401  (re-exported)
from schemas.ingestion_schema import JobStatus

logger = logging.getLogger("ingestion.refresh")

TERMINAL = {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}
PENDING = {JobStatus.QUEUED.value, JobStatus.RETRYING.value}
OUTCOMES = ("created", "unchanged", "updated", "source_changed")
COUNTERS = (
    "discovered_urls", "duplicate_urls", "ignored_urls", "jobs_created", "jobs_reused", "skipped_unchanged",
    "succeeded", "created", "unchanged", "updated", "source_changed",
    "retryable_failures", "non_retryable_failures", "unprocessed_jobs", "missing_from_sitemap",
)
MAX_EXPLICIT_PRODUCTS = 5
URI_PATTERN = re.compile(r"mongodb(?:\+srv)?://\S+|(?i:bearer)\s+\S+|(?i:x-admin-key)\S*\s*[:=]\s*\S+")


class ProductSelectionError(ValueError):
    """Explicit product input is unsafe, ambiguous, duplicated, or too large."""


def _canonical_explicit_product(value: str, policy: SourcePolicy, *, is_url: bool) -> str:
    from urllib.parse import urlsplit

    if not isinstance(value, str) or not value.strip():
        raise ProductSelectionError("Product selections must be non-empty strings")
    raw = value.strip()
    if is_url:
        parts = urlsplit(raw)
        if parts.scheme != "https" or not parts.netloc:
            raise ProductSelectionError("Product URLs must use HTTPS and include an approved host")
        try:
            path = canonical_product_path(raw, policy)
        except Exception as exc:
            raise ProductSelectionError(f"Unsafe product URL: {exc}") from exc
    else:
        if not raw.startswith("/") or "?" in raw or "#" in raw:
            raise ProductSelectionError("Product paths must be absolute paths without query or fragment")
        path = canonical_product_path(f"https://{policy.domain}{raw}", policy)
    if path is None:
        raise ProductSelectionError("Product selection must match /products/<handle>")
    return path


def select_explicit_products(
    policy: SourcePolicy, *, product_paths: list[str] | None = None, product_urls: list[str] | None = None,
) -> Discovery:
    """Canonicalize a bounded explicit selection without contacting sitemap URLs."""
    paths = list(product_paths or [])
    urls = list(product_urls or [])
    if paths and urls:
        raise ProductSelectionError("Do not mix --product-path and --product-url selections")
    values, is_url = (urls, True) if urls else (paths, False)
    if not values:
        raise ProductSelectionError("At least one explicit product selection is required")
    if len(values) > MAX_EXPLICIT_PRODUCTS:
        raise ProductSelectionError(f"At most {MAX_EXPLICIT_PRODUCTS} explicit products are allowed")
    selected = []
    for value in values:
        path = _canonical_explicit_product(value, policy, is_url=is_url)
        if path in selected:
            raise ProductSelectionError("Duplicate explicit product selection")
        selected.append(path)
    return Discovery(products={path: None for path in selected})


def redact(text: str) -> str:
    for secret in (settings.MONGODB_URI, settings.admin_api_key, settings.internal_api_token):
        if secret and len(secret) >= 4:
            text = text.replace(secret, "[redacted]")
    return URI_PATTERN.sub("[redacted]", text)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def enabled_sources() -> list[tuple[str, str, SourcePolicy]]:
    """Existing source configuration; a source that is not authorized never runs."""
    policy = SourcePolicy.from_settings()
    if not (policy.domain and policy.authorized):
        return []
    return [(settings.ingestion_source_id, settings.ingestion_source_name or policy.domain, policy)]


def commit_sha() -> str:
    for name in ("GITHUB_SHA", "RENDER_GIT_COMMIT"):
        if os.environ.get(name):
            return os.environ[name][:40]
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip()[:40] or "unknown"
    except Exception:
        return "unknown"


def _aware(value: datetime | None) -> datetime | None:
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


def _blank(source_id: str, host: str) -> dict:
    return {"source_id": source_id, "source_host": host, **{k: 0 for k in COUNTERS},
            "missing_sample": [], "error_samples": [], "termination_reason": "completed"}


async def _existing_staged(db, source_id: str) -> dict[str, dict]:
    found = {}
    async for doc in db.staged_products.find({"source_id": source_id}, {"source_url": 1, "fetched_at": 1, "status": 1}):
        found[doc["source_url"]] = doc
    return found


def _needs_refresh(existing: dict | None, lastmod: datetime | None) -> bool:
    """New products always; known ones only when the sitemap says they changed after our last fetch."""
    if existing is None:
        return True
    fetched = _aware(existing.get("fetched_at"))
    return not (lastmod and fetched and lastmod <= fetched)


async def _queue(db, source_id: str, path: str, counts: dict) -> dict | None:
    from ingestion import jobs

    job, created = await jobs.create_job(db, source_id=source_id, path=path)
    counts["jobs_created" if created else "jobs_reused"] += 1
    if not created and job["status"] in TERMINAL:
        job = await jobs.requeue_job(db, job["_id"])
    return job if job and job["status"] in PENDING else None


async def _process_batch(db, ids: list, fetcher, extractor, *, deadline: float, clock, sleep) -> bool:
    """Run the batch to completion. Returns False if the runtime cap stopped it early."""
    from ingestion.worker import process_next_job, worker_id

    me = worker_id()
    while clock() < deadline:
        if await process_next_job(db, me, fetcher, extractor, only_ids=ids):
            continue
        waiting = await db.ingestion_jobs.find_one(
            {"_id": {"$in": ids}, "status": JobStatus.RETRYING.value}, sort=[("available_at", 1)])
        if not waiting:
            return True
        delay = max((_aware(waiting["available_at"]) - datetime.now(timezone.utc)).total_seconds(), 0)
        if clock() + delay >= deadline:
            return False
        await sleep(delay)
    return False


async def _tally(db, ids: list, counts: dict) -> None:
    async for job in db.ingestion_jobs.find({"_id": {"$in": ids}}):
        status = job["status"]
        if status == JobStatus.SUCCEEDED.value:
            counts["succeeded"] += 1
            outcome = (job.get("result") or {}).get("outcome")
            if outcome in OUTCOMES:
                counts[outcome] += 1
        elif status == JobStatus.FAILED.value:
            counts["retryable_failures" if job.get("last_error_retryable") else "non_retryable_failures"] += 1
        elif status == JobStatus.RETRYING.value:
            counts["retryable_failures"] += 1
        else:
            counts["unprocessed_jobs"] += 1
        if status != JobStatus.SUCCEEDED.value and job.get("last_error") and len(counts["error_samples"]) < 5:
            counts["error_samples"].append(redact(f"{job['path']}: {job['last_error']}")[:200])


async def run_refresh(
    db, *, sources, mode: str = "once", run_id: str | None = None, sha: str | None = None,
    fetcher_factory=SafeFetcher, extractor=None, clock=time.monotonic, sleep=asyncio.sleep,
    max_seconds: int | None = None, product_paths: list[str] | None = None,
    product_urls: list[str] | None = None,
) -> dict:
    """mode: once | dry-run | discovery-only. dry-run and discovery-only never write to MongoDB."""
    started = clock()
    deadline = started + (settings.ingestion_run_max_seconds if max_seconds is None else max_seconds)
    summary = {"run_id": run_id or os.environ.get("GITHUB_RUN_ID") or uuid.uuid4().hex[:12],
               "commit_sha": sha or commit_sha(), "mode": mode, "sources": [], "termination_reason": "completed"}
    reason = None
    if not sources:
        reason = "no_authorized_sources"

    for source_id, _name, policy in sources:
        counts = _blank(source_id, policy.domain)
        summary["sources"].append(counts)
        fetcher = fetcher_factory(policy)
        try:
            found = (
                select_explicit_products(policy, product_paths=product_paths, product_urls=product_urls)
                if product_paths or product_urls
                else await discover_products(fetcher, policy, sleep=sleep)
            )
        except (DiscoveryError, ProductSelectionError) as exc:
            code = getattr(exc, "code", "product_selection_invalid")
            counts["termination_reason"] = code
            counts["error_samples"].append(redact(str(exc))[:200])
            reason = reason or code
            if code == "source_policy_violation":
                break  # never carry on past a policy violation
            continue
        counts.update(discovered_urls=len(found.products), duplicate_urls=found.duplicates, ignored_urls=found.ignored)
        if mode == "discovery-only":
            continue

        if extractor is None:
            from ingestion.extractors import ShopifyHtmlExtractor
            extractor = ShopifyHtmlExtractor()
        existing = await _existing_staged(db, source_id)
        urls = {path: source_url_for_path(path, policy) for path in found.products}
        gone = [] if (product_paths or product_urls) else sorted(set(existing) - set(urls.values()))
        counts["missing_from_sitemap"], counts["missing_sample"] = len(gone), gone[:20]  # report only
        batch, ids = [], []
        for path, lastmod in found.products.items():
            if not _needs_refresh(existing.get(urls[path]), lastmod):
                counts["skipped_unchanged"] += 1
                counts["unchanged"] += 1
            else:
                batch.append(path)
        if mode == "dry-run":
            for path in batch:
                from ingestion import jobs
                has_job = await db.ingestion_jobs.find_one({"idempotency_key": jobs.idempotency_key_for(source_id, path)})
                counts["jobs_reused" if has_job else "jobs_created"] += 1
            continue
        for path in batch:
            job = await _queue(db, source_id, path, counts)
            if job:
                ids.append(job["_id"])
        if not await _process_batch(db, ids, fetcher, extractor, deadline=deadline, clock=clock, sleep=sleep):
            counts["termination_reason"] = "runtime_limit_reached"
            reason = reason or "runtime_limit_reached"
        await _tally(db, ids, counts)
        if counts["termination_reason"] == "completed" and (
                counts["retryable_failures"] or counts["non_retryable_failures"] or counts["unprocessed_jobs"]):
            counts["termination_reason"] = "completed_with_failures"
            reason = reason or "completed_with_failures"

    totals = {k: sum(s[k] for s in summary["sources"]) for k in COUNTERS}
    summary.update(totals=totals, termination_reason=reason or "completed",
                   duration_seconds=round(clock() - started, 2))
    return summary


def render_summary(summary: dict) -> str:
    return redact(json.dumps(summary, indent=2, sort_keys=True, default=str))


async def open_db(mode: str):
    """Staging database handle. Only a real run creates indexes; dry-run opens read-only."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from database.db import ensure_indexes

    client = AsyncIOMotorClient(settings.MONGODB_URI, maxPoolSize=2, serverSelectionTimeoutMS=5000,
                                uuidRepresentation="standard")
    db = client[settings.MONGO_DB_NAME]
    await client.admin.command("ping")
    if mode == "once":
        await ensure_indexes(db)
    return client, db


async def run_cli(
    mode: str, summary_file: str | None = None, *, fetcher_factory=SafeFetcher,
    product_paths: list[str] | None = None, product_urls: list[str] | None = None,
) -> int:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    try:
        assert_staging(settings.MONGO_DB_NAME)
        client = db = None
        if mode != "discovery-only":
            client, db = await open_db(mode)
        try:
            summary = await run_refresh(
                db, sources=enabled_sources(), mode=mode, fetcher_factory=fetcher_factory,
                product_paths=product_paths, product_urls=product_urls,
            )
        finally:
            if client:
                client.close()
    except StagingGuardError as exc:
        summary = {"termination_reason": "staging_guard_failed", "error": str(exc)}
    except Exception as exc:  # no traceback: it could carry connection details
        summary = {"termination_reason": "internal_error", "error_type": type(exc).__name__}
    text = render_summary(summary)
    print(text)
    if summary_file:
        with open(summary_file, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    return 0 if summary["termination_reason"] == "completed" else 1
