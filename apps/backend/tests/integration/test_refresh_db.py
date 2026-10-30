"""One-shot monthly refresh against PostgreSQL: idempotent jobs, change detection, failure classification, safety.

Everything runs against mocked HTTP (httpx.MockTransport) and a real PostgreSQL; no live requests.
"""
import json

import httpx
import pytest

from configuration.config import settings
from ingestion import refresh
from ingestion.refresh import render_summary, run_cli, run_refresh
from ingestion.safe_fetch import DomainRateLimiter, SafeFetcher, SourcePolicy
from ingestion.sitemap import discover_products
from repositories import products as catalogue
from repositories.products import ProductInput, VariantInput
from tests.refresh_support import (  # noqa: F401  (site is a fixture)
    NEW, OLD, POLICY, ROOT, SOURCES, SCHEME, Clock, index, product_page, site, src, urlset,
)


async def go(db, site, mode="once", **kw):
    return await run_refresh(db.sessions, sources=SOURCES, mode=mode, fetcher_factory=lambda p: site.factory(p),
                             run_id="run-1", sha="a" * 40, **kw)


class _Engine:
    async def dispose(self):
        pass


# ---- finite run, queue, idempotency --------------------------------------------------------

@pytest.mark.asyncio
async def test_one_shot_run_stages_new_products_then_exits(db, site):
    summary = await go(db, site)
    assert summary["termination_reason"] == "completed" and summary["mode"] == "once"
    s = src(summary)
    assert (s["discovered_urls"], s["jobs_created"], s["succeeded"], s["created"]) == (2, 2, 2, 2)
    staged = await db.staged()
    assert {d.status for d in staged} == {"pending_review"} and len(staged) == 2
    assert {d.source_url for d in staged} == {"https://shop.example/products/a", "https://shop.example/products/b"}
    assert [j for j in await db.jobs() if j.status != "succeeded"] == []


@pytest.mark.asyncio
async def test_empty_queue_exits_successfully(db, site):
    await go(db, site)
    site.log.clear()
    again = await go(db, site)  # sitemap lastmod is older than what we fetched: nothing to do
    s = src(again)
    assert again["termination_reason"] == "completed"
    assert (s["skipped_unchanged"], s["unchanged"], s["jobs_created"], s["jobs_reused"], s["succeeded"]) == (2, 2, 0, 0, 0)
    assert site.products_fetched() == []


@pytest.mark.asyncio
async def test_summary_has_required_fields(db, site):
    summary = await go(db, site)
    assert summary["run_id"] == "run-1" and summary["commit_sha"] == "a" * 40
    required = {"source_id", "source_host", "discovered_urls", "duplicate_urls", "jobs_created", "jobs_reused", "succeeded",
                "unchanged", "updated", "source_changed", "retryable_failures", "non_retryable_failures",
                "termination_reason"}
    assert required <= set(src(summary)) and "duration_seconds" in summary and "termination_reason" in summary
    assert src(summary)["source_id"] == "shop" and src(summary)["source_host"] == "shop.example"


@pytest.mark.asyncio
async def test_unchanged_content_is_recognised_by_hash(db, site):
    await go(db, site)
    site.xml(ROOT, urlset(("https://shop.example/products/a", NEW), ("https://shop.example/products/b", NEW)))
    again = await go(db, site)
    s = src(again)
    assert (s["jobs_created"], s["jobs_reused"], s["succeeded"], s["unchanged"], s["updated"]) == (0, 2, 2, 2, 0)
    assert await db.count("ingestion_jobs") == 2  # reused, never duplicated
    assert await db.count("staged_products") == 2


@pytest.mark.asyncio
async def test_changed_pending_product_is_updated_in_place(db, site):
    await go(db, site)
    site.xml(ROOT, urlset(("https://shop.example/products/a", NEW), ("https://shop.example/products/b", OLD)))
    site.html("/products/a", product_page("a", "Alpine Shawl", price="79.00"))
    s = src(await go(db, site))
    assert (s["updated"], s["skipped_unchanged"], s["jobs_reused"]) == (1, 1, 1)
    doc = await db.staged_one(source_url="https://shop.example/products/a")
    assert float(doc.source_price) == 79.0 and doc.status == "pending_review"
    assert any(a.action == "source_updated" for a in doc.audit)


@pytest.mark.asyncio
async def test_changed_reviewed_product_is_flagged_not_overwritten(db, site):
    from repositories import staged as staged_repo

    await go(db, site)
    target = await db.staged_one(source_url="https://shop.example/products/a")
    async with db.sessions() as session, session.begin():
        await staged_repo.approve(session, target.id, price=4500, stock=1)         # reviewed through the real workflow
    before = await db.staged_one(source_url="https://shop.example/products/a")
    site.xml(ROOT, urlset(("https://shop.example/products/a", NEW), ("https://shop.example/products/b", OLD)))
    site.html("/products/a", product_page("a", "Alpine Shawl", price="79.00"))
    s = src(await go(db, site))
    assert s["source_changed"] == 1 and s["updated"] == 0
    after = await db.staged_one(source_url="https://shop.example/products/a")
    assert after.status == "approved" and after.source_price == before.source_price
    assert after.product == before.product and after.latest_source_hash != before.source_content_hash


# ---- discovery -----------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("loc", [
    "https://evil.example/products/a", "https://shop.example.evil.example/products/a", "https://sub.shop.example/products/a",
    "http://shop.example/products/a", "https://shop.example:8443/products/a", "https://user@shop.example/products/a",
    "https://127.0.0.1/products/a",
])
async def test_sitemap_url_on_unapproved_host_is_a_policy_violation(db, site, loc):
    site.xml(ROOT, urlset(("https://shop.example/products/a", OLD), (loc, OLD)))
    summary = await go(db, site)
    assert summary["termination_reason"] == "source_policy_violation"
    assert await db.count("ingestion_jobs") == 0 and site.products_fetched() == []


@pytest.mark.asyncio
async def test_a_policy_violation_stops_the_run_before_later_sources(db, site):
    other = SourcePolicy("other.example", True)
    site.xml(ROOT, urlset(("https://evil.example/products/a", OLD)))
    summary = await run_refresh(db.sessions, sources=[SOURCES[0], ("other", "Other", other)], fetcher_factory=lambda p: site.factory(p))
    assert summary["termination_reason"] == "source_policy_violation" and len(summary["sources"]) == 1


@pytest.mark.asyncio
async def test_explicit_refresh_never_fetches_the_full_sitemap(db, site):
    site.xml(ROOT, urlset(*[(f"https://shop.example/products/{handle}", OLD) for handle in "abcdef"]))
    for handle in "abcde":
        site.html(f"/products/{handle}", product_page(handle, f"Product {handle}"))
    summary = await go(db, site, product_paths=[f"/products/{handle}" for handle in "abcde"])
    assert src(summary)["discovered_urls"] == 5
    assert not any(path == ROOT for _, path in site.log)
    assert site.products_fetched() == [f"/products/{handle}" for handle in "abcde"]


@pytest.mark.asyncio
async def test_duplicate_urls_are_deduplicated_across_hosts_and_queries(db, site):
    site.xml(ROOT, urlset(("https://shop.example/products/a", OLD), ("https://www.shop.example/products/a/", NEW),
                          ("https://shop.example/products/a?variant=2", OLD), ("https://shop.example/collections/x", OLD)))
    found = await discover_products(site.factory(), POLICY)
    assert list(found.products) == ["/products/a"] and found.duplicates == 2 and found.ignored == 1
    assert found.products["/products/a"].year == 2099  # newest lastmod wins
    summary = await go(db, site)
    assert src(summary)["jobs_created"] == 1 and await db.count("staged_products") == 1


@pytest.mark.asyncio
async def test_www_and_apex_listings_stage_one_canonical_product(db, site):
    site.xml(ROOT, urlset(("https://www.shop.example/products/a", OLD)))
    await go(db, site)
    doc = await db.staged_one()
    assert doc.source_url == "https://shop.example/products/a" and await db.count("staged_products") == 1


@pytest.mark.asyncio
async def test_url_cap_fails_clearly_without_partial_processing(db, site, monkeypatch):
    assert settings.ingestion_max_urls_per_source == 500 and settings.ingestion_run_max_seconds == 2700
    monkeypatch.setattr(settings, "ingestion_max_urls_per_source", 1)
    summary = await go(db, site)
    assert summary["termination_reason"] == "discovery_limit_exceeded"
    assert src(summary)["termination_reason"] == "discovery_limit_exceeded"
    assert await db.count("ingestion_jobs") == 0 and site.products_fetched() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("response,code", [
    ((404, "text/html", "nope"), "sitemap_unavailable"),
    ((500, "application/xml", "boom"), "sitemap_unavailable"),
    ((200, "application/xml", "<urlset"), "sitemap_invalid"),
    ((200, "application/xml", '<!DOCTYPE x [<!ENTITY a "b">]><urlset></urlset>'), "sitemap_invalid"),
    ((200, "application/xml", "<html></html>"), "sitemap_invalid"),
    ((200, "text/html", "<urlset></urlset>"), "sitemap_unavailable"),
    ((200, "application/xml", urlset(("https://shop.example/collections/all", OLD))), "sitemap_empty"),
])
async def test_missing_or_bad_sitemap_fails_the_run(db, site, response, code):
    site.pages[ROOT] = response
    summary = await go(db, site)
    assert summary["termination_reason"] == code
    assert await db.count("ingestion_jobs") == 0


@pytest.mark.asyncio
async def test_no_authorized_sources_is_a_failure_not_a_silent_success(db, site):
    summary = await run_refresh(db.sessions, sources=[], fetcher_factory=lambda p: site.factory(p))
    assert summary["termination_reason"] == "no_authorized_sources"


@pytest.mark.asyncio
async def test_new_site_in_a_sitemap_is_never_treated_as_authorized(db, site):
    site.xml(ROOT, urlset(("https://brand-new-shop.example/products/a", OLD)))
    summary = await go(db, site)
    assert summary["termination_reason"] == "source_policy_violation"
    assert not any(host == "brand-new-shop.example" for host, _ in site.log)


# ---- failures and retryability -------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("status,retryable", [(429, True), (500, True), (503, True), (404, False), (403, False)])
async def test_http_failures_are_classified(db, site, status, retryable):
    site.html("/products/b", "x", status=status)
    summary = await go(db, site)
    s = src(summary)
    assert s["succeeded"] == 1
    assert (s["retryable_failures"], s["non_retryable_failures"]) == ((1, 0) if retryable else (0, 1))
    assert summary["termination_reason"] == "completed_with_failures"
    job = await db.job(path="/products/b")
    assert job.attempts == (3 if retryable else 1) and job.status == "failed"
    assert job.last_error_retryable is retryable            # the flag persists


@pytest.mark.asyncio
async def test_timeouts_and_connection_failures_are_retryable(db, site):
    def boom(request):
        if request.url.path == "/products/b":
            raise httpx.ConnectTimeout("t")
        return site.handler(request)

    async def dns(_):
        return ["93.184.216.34"]
    summary = await run_refresh(db.sessions, sources=SOURCES, run_id="r", sha="s", fetcher_factory=lambda p: SafeFetcher(
        p, resolver=dns, rate_limiter=DomainRateLimiter(0),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(boom))))
    assert (src(summary)["retryable_failures"], src(summary)["non_retryable_failures"]) == (1, 0)


@pytest.mark.asyncio
async def test_temporary_dns_failure_is_retryable_and_private_ip_is_not(db, site):
    from ingestion.safe_fetch import FetchError

    async def flaky_dns(host):
        raise FetchError("DNS resolution failed", retryable=True)

    async def private_dns(host):
        return ["10.0.0.5"]
    for resolver, expected in ((flaky_dns, (1, 0)), (private_dns, (0, 1))):
        await db.clear()
        calls = {"n": 0}

        def factory(policy, resolver=resolver):
            async def dns(host):
                calls["n"] += 1
                return ["93.184.216.34"] if calls["n"] <= 1 else await resolver(host)  # sitemap resolves, products do not
            return SafeFetcher(policy, resolver=dns, rate_limiter=DomainRateLimiter(0),
                               client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(site.handler)))
        site.xml(ROOT, urlset(("https://shop.example/products/a", OLD)))
        s = src(await run_refresh(db.sessions, sources=SOURCES, fetcher_factory=factory))
        assert (s["retryable_failures"], s["non_retryable_failures"]) == expected


@pytest.mark.asyncio
async def test_unsafe_redirect_oversized_and_bad_data_are_not_retried(db, site, monkeypatch):
    site.xml(ROOT, urlset(*[(f"https://shop.example/products/{h}", OLD) for h in "cdef"]))
    async def dns(_): return ["93.184.216.34"]
    pages = {
        "/products/c": httpx.Response(302, headers={"location": "https://evil.example/products/c"}),
        "/products/d": httpx.Response(200, headers={"content-type": "text/html"}, text="x" * 5000),
        "/products/e": httpx.Response(200, headers={"content-type": "text/html"}, text="<html><head><title>Only a title</title></head></html>"),
        "/products/f": httpx.Response(200, headers={"content-type": "application/pdf"}, text="%PDF"),
    }

    def handler(request):
        return pages.get(request.url.path) or site.handler(request)
    monkeypatch.setattr(settings, "ingestion_max_response_bytes", 4000)
    summary = await run_refresh(db.sessions, sources=SOURCES, fetcher_factory=lambda p: SafeFetcher(
        p, resolver=dns, rate_limiter=DomainRateLimiter(0),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))))
    s = src(summary)
    assert (s["retryable_failures"], s["non_retryable_failures"], s["succeeded"]) == (0, 4, 0)
    assert {j.attempts for j in await db.jobs()} == {1}
    assert {j.last_error_retryable for j in await db.jobs()} == {False}


@pytest.mark.asyncio
async def test_one_failure_does_not_stop_the_rest_of_the_batch(db, site):
    site.html("/products/a", "x", status=404)
    s = src(await go(db, site))
    assert (s["succeeded"], s["non_retryable_failures"]) == (1, 1)


@pytest.mark.asyncio
async def test_failed_job_is_requeued_on_the_next_run(db, site):
    site.html("/products/b", "x", status=404)
    await go(db, site)
    site.html("/products/b", product_page("b", "Birch Scarf"))
    s = src(await go(db, site))
    assert (s["jobs_reused"], s["succeeded"], s["created"]) == (1, 1, 1) and await db.count("ingestion_jobs") == 2


# ---- runtime and request limits ------------------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_cap_stops_the_run_and_reports_it(db, site):
    clock = Clock()

    class SlowFetcher(SafeFetcher):
        async def fetch(self, url, **kw):
            clock.t += 1000 if url.endswith(("/a", "/b")) else 0
            return await super().fetch(url, **kw)
    async def dns(_): return ["93.184.216.34"]
    summary = await run_refresh(db.sessions, sources=SOURCES, clock=clock, max_seconds=1500, fetcher_factory=lambda p: SlowFetcher(
        p, resolver=dns, rate_limiter=DomainRateLimiter(0),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(site.handler))))
    s = src(summary)
    assert summary["termination_reason"] == "runtime_limit_reached"
    assert s["succeeded"] == 2 or s["succeeded"] == 1
    assert s["succeeded"] + s["unprocessed_jobs"] == 2
    assert len(site.products_fetched()) <= 2


@pytest.mark.asyncio
async def test_jobs_are_processed_one_at_a_time_with_a_bounded_attempt_count(db, site):
    active, peak = {"n": 0}, {"n": 0}
    original = site.handler

    class Tracking(SafeFetcher):
        async def fetch(self, url, **kw):
            active["n"] += 1; peak["n"] = max(peak["n"], active["n"])
            try:
                return await super().fetch(url, **kw)
            finally:
                active["n"] -= 1
    async def dns(_): return ["93.184.216.34"]
    await run_refresh(db.sessions, sources=SOURCES, fetcher_factory=lambda p: Tracking(
        p, resolver=dns, rate_limiter=DomainRateLimiter(0),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(original))))
    assert peak["n"] == 1
    assert settings.ingestion_job_max_attempts == 3 and settings.ingestion_domain_min_interval_seconds == 2.0
    assert {j.max_attempts for j in await db.jobs()} == {3}


@pytest.mark.asyncio
async def test_a_run_only_processes_its_own_batch(db, site):
    stray, _ = await db.create_job("/products/stray", source_id="shop")
    site.xml(ROOT, urlset(("https://shop.example/products/a", OLD)))
    await go(db, site)
    assert "/products/stray" not in site.products_fetched()
    assert (await db.job(id=stray.id)).status == "queued"


# ---- never publish / archive / delete -------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_products_are_reported_and_left_alone(db, site):
    await go(db, site)
    site.xml(ROOT, urlset(("https://shop.example/products/a", OLD)))
    before = await db.snapshot()
    summary = await go(db, site)
    s = src(summary)
    assert s["missing_from_sitemap"] == 1 and s["missing_sample"] == ["https://shop.example/products/b"]
    assert await db.snapshot() == before
    assert (await db.staged_one(source_url="https://shop.example/products/b")).status == "pending_review"


@pytest.mark.asyncio
async def test_refresh_never_approves_publishes_or_touches_products(db, site):
    async with db.sessions() as session, session.begin():
        await catalogue.create_product(session, ProductInput(
            slug="live", name="Live", cover_image_url="u", status="active",
            variants=[VariantInput(name="v", image_url="u", price=1, stock=1)]))
    live_before = [(p.name, p.is_active, p.status, p.revision) for p in await db.products()]
    await go(db, site)
    site.xml(ROOT, urlset(("https://shop.example/products/a", NEW)))
    await go(db, site)
    assert [(p.name, p.is_active, p.status, p.revision) for p in await db.products()] == live_before == [("Live", True, "active", 1)]
    staged = await db.staged()
    assert {d.status for d in staged} == {"pending_review"}
    for doc in staged:
        assert doc.product_id is None and doc.stock_known is False
        assert all(a.action in {"staged", "source_updated", "source_changed"} for a in doc.audit)


# ---- dry-run --------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_plans_but_writes_nothing(db, site):
    await go(db, site)
    site.xml(ROOT, urlset(("https://shop.example/products/a", NEW), ("https://shop.example/products/c", OLD)))
    before = await db.snapshot()
    site.log.clear()
    summary = await go(db, site, mode="dry-run")
    assert await db.snapshot() == before
    s = src(summary)
    assert (s["jobs_created"], s["jobs_reused"], s["missing_from_sitemap"], s["succeeded"]) == (1, 1, 1, 0)
    assert site.products_fetched() == []  # not even product pages are requested


@pytest.mark.asyncio
async def test_dry_run_on_an_empty_database_writes_no_rows(db, site):
    empty = await db.snapshot()
    summary = await go(db, site, mode="dry-run")
    assert src(summary)["jobs_created"] == 2 and await db.snapshot() == empty


# ---- CLI with a real database ---------------------------------------------------------------

def _staging(monkeypatch, name="elegance_shawls_staging"):
    monkeypatch.setattr(settings, "database_url", f"{SCHEME}u:p@localhost/{name}")
    monkeypatch.setattr(settings, "ingestion_source_domain", "shop.example")
    monkeypatch.setattr(settings, "ingestion_source_authorized", True)


@pytest.mark.asyncio
async def test_cli_runs_once_prints_a_summary_and_writes_the_file(monkeypatch, db, site, capsys, tmp_path):
    _staging(monkeypatch)
    monkeypatch.setattr(settings, "ingestion_source_id", "shop")
    monkeypatch.setattr(settings, "ingestion_allowed_hosts", "www.shop.example")
    monkeypatch.setattr(settings, "ingestion_image_hosts", "cdn.shopify.com")

    async def fake_open(mode): return _Engine(), db.sessions
    monkeypatch.setattr(refresh, "open_db", fake_open)
    target = tmp_path / "summary.json"
    code = await run_cli("once", str(target), fetcher_factory=lambda p: site.factory(p))
    printed = json.loads(capsys.readouterr().out)
    assert code == 0 and printed["termination_reason"] == "completed"
    assert json.loads(target.read_text()) == printed and printed["totals"]["succeeded"] == 2


@pytest.mark.asyncio
async def test_cli_exit_code_is_non_zero_on_any_incomplete_run(monkeypatch, db, site, capsys):
    _staging(monkeypatch)

    async def fake_open(mode): return _Engine(), db.sessions
    monkeypatch.setattr(refresh, "open_db", fake_open)
    site.pages[ROOT] = (404, "text/html", "gone")
    assert await run_cli("once", fetcher_factory=lambda p: site.factory(p)) == 1


@pytest.mark.asyncio
async def test_error_samples_in_a_real_run_carry_no_secrets(db, site, monkeypatch):
    monkeypatch.setattr(settings, "database_url", SCHEME + "user:hunter2@host/db")
    site.html("/products/b", "x", status=404)
    text = render_summary(await go(db, site))
    assert "hunter2" not in text and SCHEME not in text and "/products/b" in text


@pytest.mark.asyncio
async def test_only_the_database_aware_modes_open_the_database(monkeypatch, db, site):
    _staging(monkeypatch)
    opened = []

    async def fake_open(mode):
        opened.append(mode)
        return _Engine(), db.sessions
    monkeypatch.setattr(refresh, "open_db", fake_open)
    for mode in ("discovery-only", "dry-run", "once"):
        await run_cli(mode, fetcher_factory=lambda p: site.factory(p))
    assert opened == ["dry-run", "once"]
    assert await db.count("ingestion_jobs") == 2  # only --once created jobs; dry-run still read the database


@pytest.mark.asyncio
async def test_the_real_open_db_connects_to_the_configured_database(monkeypatch, db, migrated_url):
    monkeypatch.setattr(settings, "database_url", migrated_url)
    engine, sessions = await refresh.open_db("once")
    try:
        async with sessions() as session:
            from sqlalchemy import text
            assert (await session.execute(text("select 1"))).scalar() == 1
    finally:
        await engine.dispose()
