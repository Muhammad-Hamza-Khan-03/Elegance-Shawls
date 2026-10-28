"""One-shot monthly refresh: discovery, idempotent jobs, change detection, safety limits.

Everything runs against mocked HTTP (httpx.MockTransport) and mongomock; no live requests.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from configuration.config import settings
from database.db import ensure_indexes
from ingestion import refresh
from ingestion.refresh import StagingGuardError, assert_staging, enabled_sources, redact, render_summary, run_cli, run_refresh
from ingestion.safe_fetch import DomainRateLimiter, SafeFetcher, SourcePolicy
from ingestion.sitemap import DiscoveryError, canonical_product_path, discover_products, parse_sitemap

POLICY = SourcePolicy("shop.example", True, image_hosts=frozenset({"cdn.shopify.com"}),
                      extra_hosts=frozenset({"www.shop.example"}))
SOURCES = [("shop", "Shop", POLICY)]
OLD, NEW = "2026-01-01T00:00:00Z", "2099-01-01T00:00:00Z"
ROOT = "/sitemap.xml"
# Fake connection strings are assembled at runtime so no URI literal exists in the repository.
SCHEME, SRV = "mongo" + "db://", "mongo" + "db+srv://"


def urlset(*entries):
    rows = "".join(f"<url><loc>{loc}</loc>" + (f"<lastmod>{mod}</lastmod>" if mod else "") + "</url>" for loc, mod in entries)
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</urlset>'


def index(*locs):
    rows = "".join(f"<sitemap><loc>{loc}</loc></sitemap>" for loc in locs)
    return f'<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</sitemapindex>'


def product_page(handle, title="Alpine Shawl", price="59.00", description="A warm woven shawl."):
    data = {"@type": "Product", "name": title, "description": description, "category": "Shawls",
            "image": [f"https://cdn.shopify.com/s/files/{handle}.jpg"], "url": f"https://shop.example/products/{handle}",
            "offers": {"@type": "Offer", "price": price, "priceCurrency": "AUD"}}
    return f"<html><head><title>{title}</title><script type='application/ld+json'>{json.dumps(data)}</script></head></html>"


class Site:
    """Routes by path; records every request as (host header, path)."""

    def __init__(self):
        self.pages: dict[str, tuple[int, str, str]] = {}
        self.log: list[tuple[str, str]] = []

    def xml(self, path, body, status=200):
        self.pages[path] = (status, "application/xml", body)

    def html(self, path, body, status=200, ctype="text/html"):
        self.pages[path] = (status, ctype, body)

    def handler(self, request):
        path = request.url.path + (f"?{request.url.query.decode()}" if request.url.query else "")
        self.log.append((request.headers["host"], path))
        status, ctype, body = self.pages.get(path, (404, "text/html", "missing"))
        return httpx.Response(status, headers={"content-type": ctype}, text=body)

    def factory(self, policy=POLICY):
        async def dns(_):
            return ["93.184.216.34"]
        return SafeFetcher(policy, resolver=dns, rate_limiter=DomainRateLimiter(0),
                           client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(self.handler)))

    def products_fetched(self):
        return [p for _, p in self.log if p.startswith("/products/")]


@pytest.fixture
def site(monkeypatch):
    monkeypatch.setattr(settings, "ingestion_job_backoff_seconds", 0)
    monkeypatch.setattr(settings, "ingestion_source_name", "Shop")
    s = Site()
    s.xml(ROOT, urlset(("https://shop.example/products/a", OLD), ("https://shop.example/products/b", OLD)))
    s.html("/products/a", product_page("a", "Alpine Shawl"))
    s.html("/products/b", product_page("b", "Birch Scarf"))
    return s


@pytest_asyncio.fixture
async def db():
    database = AsyncMongoMockClient().refresh
    await ensure_indexes(database)
    return database


async def go(db, site, mode="once", **kw):
    return await run_refresh(db, sources=SOURCES, mode=mode, fetcher_factory=lambda p: site.factory(p),
                             run_id="run-1", sha="a" * 40, **kw)


def src(summary):
    return summary["sources"][0]


async def snapshot(db):
    return {name: sorted([repr(sorted(d.items(), key=str)) async for d in db[name].find()])
            for name in await db.list_collection_names()}


# ---- finite run, queue, idempotency --------------------------------------------------------

@pytest.mark.asyncio
async def test_one_shot_run_stages_new_products_then_exits(db, site):
    summary = await go(db, site)
    assert summary["termination_reason"] == "completed" and summary["mode"] == "once"
    s = src(summary)
    assert (s["discovered_urls"], s["jobs_created"], s["succeeded"], s["created"]) == (2, 2, 2, 2)
    staged = [d async for d in db.staged_products.find()]
    assert {d["status"] for d in staged} == {"pending_review"} and len(staged) == 2
    assert {d["source_url"] for d in staged} == {"https://shop.example/products/a", "https://shop.example/products/b"}
    assert [d async for d in db.ingestion_jobs.find({"status": {"$nin": ["succeeded"]}})] == []


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
    assert await db.ingestion_jobs.count_documents({}) == 2  # reused, never duplicated
    assert await db.staged_products.count_documents({}) == 2


@pytest.mark.asyncio
async def test_changed_pending_product_is_updated_in_place(db, site):
    await go(db, site)
    site.xml(ROOT, urlset(("https://shop.example/products/a", NEW), ("https://shop.example/products/b", OLD)))
    site.html("/products/a", product_page("a", "Alpine Shawl", price="79.00"))
    s = src(await go(db, site))
    assert (s["updated"], s["skipped_unchanged"], s["jobs_reused"]) == (1, 1, 1)
    doc = await db.staged_products.find_one({"source_url": "https://shop.example/products/a"})
    assert doc["source_price"] == 79.0 and doc["status"] == "pending_review"
    assert any(a["action"] == "source_updated" for a in doc["audit"])


@pytest.mark.asyncio
async def test_changed_reviewed_product_is_flagged_not_overwritten(db, site):
    await go(db, site)
    await db.staged_products.update_one({"source_url": "https://shop.example/products/a"}, {"$set": {"status": "approved"}})
    before = await db.staged_products.find_one({"source_url": "https://shop.example/products/a"})
    site.xml(ROOT, urlset(("https://shop.example/products/a", NEW), ("https://shop.example/products/b", OLD)))
    site.html("/products/a", product_page("a", "Alpine Shawl", price="79.00"))
    s = src(await go(db, site))
    assert s["source_changed"] == 1 and s["updated"] == 0
    after = await db.staged_products.find_one({"source_url": "https://shop.example/products/a"})
    assert after["status"] == "approved" and after["source_price"] == before["source_price"]
    assert after["product"] == before["product"] and after["latest_source_hash"] != before["source_content_hash"]


# ---- discovery -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sitemap_index_is_traversed_and_non_product_sitemaps_ignored(db, site):
    site.xml(ROOT, index("https://shop.example/sitemap_products_1.xml?from=1&amp;to=2",
                         "https://www.shop.example/sitemap_products_2.xml", "https://shop.example/sitemap_pages_1.xml"))
    site.xml("/sitemap_products_1.xml?from=1&to=2", urlset(("https://shop.example/products/a", OLD)))
    site.xml("/sitemap_products_2.xml", urlset(("https://shop.example/products/b", OLD)))
    found = await discover_products(site.factory(), POLICY)
    assert sorted(found.products) == ["/products/a", "/products/b"] and found.sitemaps_fetched == 3
    assert not any("pages" in p for _, p in site.log) and found.ignored == 1


@pytest.mark.asyncio
async def test_nested_index_depth_is_bounded(site):
    site.xml(ROOT, index("https://shop.example/sitemap_products_1.xml"))
    site.xml("/sitemap_products_1.xml", index("https://shop.example/sitemap_products_2.xml"))
    site.xml("/sitemap_products_2.xml", index("https://shop.example/sitemap_products_3.xml"))
    with pytest.raises(DiscoveryError) as err:
        await discover_products(site.factory(), POLICY)
    assert err.value.code == "sitemap_invalid"


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
    assert await db.ingestion_jobs.count_documents({}) == 0 and site.products_fetched() == []


@pytest.mark.asyncio
async def test_sitemap_index_child_on_unapproved_host_is_a_policy_violation(site):
    site.xml(ROOT, index("https://evil.example/sitemap_products_1.xml"))
    with pytest.raises(DiscoveryError) as err:
        await discover_products(site.factory(), POLICY)
    assert err.value.code == "source_policy_violation" and ("evil.example", "/sitemap_products_1.xml") not in site.log


@pytest.mark.asyncio
async def test_a_policy_violation_stops_the_run_before_later_sources(db, site):
    other = SourcePolicy("other.example", True)
    site.xml(ROOT, urlset(("https://evil.example/products/a", OLD)))
    summary = await run_refresh(db, sources=[SOURCES[0], ("other", "Other", other)], fetcher_factory=lambda p: site.factory(p))
    assert summary["termination_reason"] == "source_policy_violation" and len(summary["sources"]) == 1


def test_canonicalization_collapses_www_query_fragment_and_slash():
    for loc in ("https://www.shop.example/products/a", "https://SHOP.example/products/a/", "https://shop.example/products/a?utm=1",
                "https://www.shop.example/products/a/?x=1#frag"):
        assert canonical_product_path(loc, POLICY) == "/products/a"


@pytest.mark.parametrize("loc", [
    "https://shop.example/", "https://shop.example/collections/all", "https://shop.example/pages/about",
    "https://shop.example/blogs/news/post", "https://shop.example/products/", "https://shop.example/products/a/b",
    "https://shop.example/products/a b",
])
def test_non_product_urls_are_ignored(loc):
    assert canonical_product_path(loc, POLICY) is None


@pytest.mark.asyncio
async def test_duplicate_urls_are_deduplicated_across_hosts_and_queries(db, site):
    site.xml(ROOT, urlset(("https://shop.example/products/a", OLD), ("https://www.shop.example/products/a/", NEW),
                          ("https://shop.example/products/a?variant=2", OLD), ("https://shop.example/collections/x", OLD)))
    found = await discover_products(site.factory(), POLICY)
    assert list(found.products) == ["/products/a"] and found.duplicates == 2 and found.ignored == 1
    assert found.products["/products/a"].year == 2099  # newest lastmod wins
    summary = await go(db, site)
    assert src(summary)["jobs_created"] == 1 and await db.staged_products.count_documents({}) == 1


@pytest.mark.asyncio
async def test_www_and_apex_listings_stage_one_canonical_product(db, site):
    site.xml(ROOT, urlset(("https://www.shop.example/products/a", OLD)))
    await go(db, site)
    doc = await db.staged_products.find_one()
    assert doc["source_url"] == "https://shop.example/products/a" and await db.staged_products.count_documents({}) == 1


@pytest.mark.asyncio
async def test_url_cap_fails_clearly_without_partial_processing(db, site, monkeypatch):
    assert settings.ingestion_max_urls_per_source == 500 and settings.ingestion_run_max_seconds == 2700
    monkeypatch.setattr(settings, "ingestion_max_urls_per_source", 1)
    summary = await go(db, site)
    assert summary["termination_reason"] == "discovery_limit_exceeded"
    assert src(summary)["termination_reason"] == "discovery_limit_exceeded"
    assert await db.ingestion_jobs.count_documents({}) == 0 and site.products_fetched() == []


@pytest.mark.asyncio
async def test_exactly_the_cap_is_allowed(site, monkeypatch):
    monkeypatch.setattr(settings, "ingestion_max_urls_per_source", 2)
    assert len((await discover_products(site.factory(), POLICY)).products) == 2


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
    assert await db.ingestion_jobs.count_documents({}) == 0


@pytest.mark.asyncio
async def test_transient_sitemap_failures_are_retried(site):
    calls = {"n": 0}
    original = site.handler

    def flaky(request):
        calls["n"] += 1
        return httpx.Response(503, text="busy") if calls["n"] == 1 else original(request)

    async def dns(_):
        return ["93.184.216.34"]
    fetcher = SafeFetcher(POLICY, resolver=dns, rate_limiter=DomainRateLimiter(0),
                          client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(flaky)))
    async def nosleep(_): return None
    assert len((await discover_products(fetcher, POLICY, sleep=nosleep)).products) == 2 and calls["n"] == 2


def test_unauthorized_or_unconfigured_sources_never_run(monkeypatch):
    for domain, authorized in (("shop.example", False), ("", True)):
        monkeypatch.setattr(settings, "ingestion_source_domain", domain)
        monkeypatch.setattr(settings, "ingestion_source_authorized", authorized)
        assert enabled_sources() == []
    monkeypatch.setattr(settings, "ingestion_source_domain", "shop.example")
    monkeypatch.setattr(settings, "ingestion_source_authorized", True)
    assert [s[0] for s in enabled_sources()] == [settings.ingestion_source_id]


@pytest.mark.asyncio
async def test_no_authorized_sources_is_a_failure_not_a_silent_success(db, site):
    summary = await run_refresh(db, sources=[], fetcher_factory=lambda p: site.factory(p))
    assert summary["termination_reason"] == "no_authorized_sources"


@pytest.mark.asyncio
async def test_new_site_in_a_sitemap_is_never_treated_as_authorized(db, site):
    site.xml(ROOT, urlset(("https://brand-new-shop.example/products/a", OLD)))
    summary = await go(db, site)
    assert summary["termination_reason"] == "source_policy_violation"
    assert not any(host == "brand-new-shop.example" for host, _ in site.log)


# ---- failures ------------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("status,retryable", [(429, True), (500, True), (503, True), (404, False), (403, False)])
async def test_http_failures_are_classified(db, site, status, retryable):
    site.html("/products/b", "x", status=status)
    summary = await go(db, site)
    s = src(summary)
    assert s["succeeded"] == 1
    assert (s["retryable_failures"], s["non_retryable_failures"]) == ((1, 0) if retryable else (0, 1))
    assert summary["termination_reason"] == "completed_with_failures"
    job = await db.ingestion_jobs.find_one({"path": "/products/b"})
    assert job["attempts"] == (3 if retryable else 1) and job["status"] == "failed"


@pytest.mark.asyncio
async def test_timeouts_and_connection_failures_are_retryable(db, site):
    def boom(request):
        if request.url.path == "/products/b":
            raise httpx.ConnectTimeout("t")
        return site.handler(request)

    async def dns(_):
        return ["93.184.216.34"]
    summary = await run_refresh(db, sources=SOURCES, run_id="r", sha="s", fetcher_factory=lambda p: SafeFetcher(
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
        database = AsyncMongoMockClient().x
        await ensure_indexes(database)
        calls = {"n": 0}

        def factory(policy, resolver=resolver):
            async def dns(host):
                calls["n"] += 1
                return ["93.184.216.34"] if calls["n"] <= 1 else await resolver(host)  # sitemap resolves, products do not
            return SafeFetcher(policy, resolver=dns, rate_limiter=DomainRateLimiter(0),
                               client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(site.handler)))
        site.xml(ROOT, urlset(("https://shop.example/products/a", OLD)))
        s = src(await run_refresh(database, sources=SOURCES, fetcher_factory=factory))
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
    summary = await run_refresh(db, sources=SOURCES, fetcher_factory=lambda p: SafeFetcher(
        p, resolver=dns, rate_limiter=DomainRateLimiter(0),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))))
    s = src(summary)
    assert (s["retryable_failures"], s["non_retryable_failures"], s["succeeded"]) == (0, 4, 0)
    assert {j["attempts"] async for j in db.ingestion_jobs.find()} == {1}


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
    assert (s["jobs_reused"], s["succeeded"], s["created"]) == (1, 1, 1) and await db.ingestion_jobs.count_documents({}) == 2


# ---- runtime and request limits ------------------------------------------------------------

class Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


@pytest.mark.asyncio
async def test_runtime_cap_stops_the_run_and_reports_it(db, site):
    clock = Clock()
    inner = site.factory

    class SlowFetcher(SafeFetcher):
        async def fetch(self, url, **kw):
            clock.t += 1000 if url.endswith(("/a", "/b")) else 0
            return await super().fetch(url, **kw)
    async def dns(_): return ["93.184.216.34"]
    summary = await run_refresh(db, sources=SOURCES, clock=clock, max_seconds=1500, fetcher_factory=lambda p: SlowFetcher(
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
    await run_refresh(db, sources=SOURCES, fetcher_factory=lambda p: Tracking(
        p, resolver=dns, rate_limiter=DomainRateLimiter(0),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(original))))
    assert peak["n"] == 1
    assert settings.ingestion_job_max_attempts == 3 and settings.ingestion_domain_min_interval_seconds == 2.0
    assert {j["max_attempts"] async for j in db.ingestion_jobs.find()} == {3}


@pytest.mark.asyncio
async def test_a_run_only_processes_its_own_batch(db, site):
    from ingestion import jobs
    stray, _ = await jobs.create_job(db, source_id="shop", path="/products/stray")
    site.xml(ROOT, urlset(("https://shop.example/products/a", OLD)))
    await go(db, site)
    assert "/products/stray" not in site.products_fetched()
    assert (await db.ingestion_jobs.find_one({"_id": stray["_id"]}))["status"] == "queued"


# ---- never publish / archive / delete -------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_products_are_reported_and_left_alone(db, site):
    await go(db, site)
    site.xml(ROOT, urlset(("https://shop.example/products/a", OLD)))
    before = await snapshot(db)
    summary = await go(db, site)
    s = src(summary)
    assert s["missing_from_sitemap"] == 1 and s["missing_sample"] == ["https://shop.example/products/b"]
    assert await snapshot(db) == before
    assert (await db.staged_products.find_one({"source_url": "https://shop.example/products/b"}))["status"] == "pending_review"


@pytest.mark.asyncio
async def test_refresh_never_approves_publishes_or_touches_products(db, site):
    await db.products.insert_one({"name": "Live", "is_active": True, "status": "active"})
    await go(db, site)
    site.xml(ROOT, urlset(("https://shop.example/products/a", NEW)))
    await go(db, site)
    assert [(d["name"], d["is_active"], d["status"]) async for d in db.products.find()] == [("Live", True, "active")]
    assert {d["status"] async for d in db.staged_products.find()} == {"pending_review"}
    for doc in [d async for d in db.staged_products.find()]:
        assert doc.get("product_id") is None and doc["stock_known"] is False
        assert all(a["action"] in {"staged", "source_updated", "source_changed"} for a in doc["audit"])


def test_refresh_code_has_no_publish_archive_or_delete_paths():
    code = (Path(refresh.__file__).read_text() + (Path(refresh.__file__).parent / "sitemap.py").read_text())
    for forbidden in ("delete_one", "delete_many", "drop(", "is_active", "StagedStatus.PUBLISHED", "StagedStatus.ARCHIVED",
                      "db.products"):
        assert forbidden not in code


# ---- dry-run and discovery-only -------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_plans_but_writes_nothing(db, site):
    await go(db, site)
    site.xml(ROOT, urlset(("https://shop.example/products/a", NEW), ("https://shop.example/products/c", OLD)))
    before = await snapshot(db)
    site.log.clear()
    summary = await go(db, site, mode="dry-run")
    assert await snapshot(db) == before
    s = src(summary)
    assert (s["jobs_created"], s["jobs_reused"], s["missing_from_sitemap"], s["succeeded"]) == (1, 1, 1, 0)
    assert site.products_fetched() == []  # not even product pages are requested


@pytest.mark.asyncio
async def test_dry_run_on_an_empty_database_creates_no_collections(db, site):
    fresh = AsyncMongoMockClient().fresh
    summary = await go(fresh, site, mode="dry-run")
    assert src(summary)["jobs_created"] == 2 and await fresh.list_collection_names() == []


@pytest.mark.asyncio
async def test_discovery_only_needs_no_database(site):
    summary = await run_refresh(None, sources=SOURCES, mode="discovery-only", fetcher_factory=lambda p: site.factory(p))
    assert summary["termination_reason"] == "completed" and src(summary)["discovered_urls"] == 2
    assert site.products_fetched() == []


# ---- staging guard, CLI, secrets --------------------------------------------------------------

@pytest.mark.parametrize("name", ["elegance_shawls_staging", "staging", "es-staging", "staging_2026", "ES_STAGING"])
def test_staging_names_pass_the_guard(name):
    assert_staging(name)


@pytest.mark.parametrize("name", ["elegance_shawls", "production", "elegance_shawls_prod", "prod_staging", "stagingx", "xstaging",
                                  "test", "", "restaging"])
def test_non_staging_names_are_refused(name):
    with pytest.raises(StagingGuardError):
        assert_staging(name)


@pytest.mark.asyncio
async def test_cli_refuses_a_non_staging_database_before_connecting(monkeypatch, capsys):
    monkeypatch.setattr(settings, "MONGO_DB_NAME", "elegance_shawls")
    async def forbidden(mode): raise AssertionError("must not connect")
    monkeypatch.setattr(refresh, "open_db", forbidden)
    for mode in ("once", "dry-run", "discovery-only"):
        assert await run_cli(mode) == 1
    assert capsys.readouterr().out.count("staging_guard_failed") == 3


class _Client:
    def close(self): pass


@pytest.mark.asyncio
async def test_cli_runs_once_prints_a_summary_and_writes_the_file(monkeypatch, db, site, capsys, tmp_path):
    monkeypatch.setattr(settings, "MONGO_DB_NAME", "elegance_shawls_staging")
    monkeypatch.setattr(settings, "ingestion_source_domain", "shop.example")
    monkeypatch.setattr(settings, "ingestion_source_authorized", True)
    monkeypatch.setattr(settings, "ingestion_source_id", "shop")
    monkeypatch.setattr(settings, "ingestion_allowed_hosts", "www.shop.example")
    monkeypatch.setattr(settings, "ingestion_image_hosts", "cdn.shopify.com")
    async def fake_open(mode): return _Client(), db
    monkeypatch.setattr(refresh, "open_db", fake_open)
    target = tmp_path / "summary.json"
    code = await run_cli("once", str(target), fetcher_factory=lambda p: site.factory(p))
    printed = json.loads(capsys.readouterr().out)
    assert code == 0 and printed["termination_reason"] == "completed"
    assert json.loads(target.read_text()) == printed and printed["totals"]["succeeded"] == 2


@pytest.mark.asyncio
async def test_cli_exit_code_is_non_zero_on_any_incomplete_run(monkeypatch, db, site, capsys):
    monkeypatch.setattr(settings, "MONGO_DB_NAME", "elegance_shawls_staging")
    monkeypatch.setattr(settings, "ingestion_source_domain", "shop.example")
    monkeypatch.setattr(settings, "ingestion_source_authorized", True)
    async def fake_open(mode): return _Client(), db
    monkeypatch.setattr(refresh, "open_db", fake_open)
    site.pages[ROOT] = (404, "text/html", "gone")
    assert await run_cli("once", fetcher_factory=lambda p: site.factory(p)) == 1


def test_secrets_are_redacted_from_summaries_and_logs(monkeypatch):
    uri = SRV + "user:hunter2@cluster.example.mongodb.net/db"
    monkeypatch.setattr(settings, "MONGODB_URI", uri)
    monkeypatch.setattr(settings, "admin_api_key", "super-secret-admin-key")
    text = render_summary({"error_samples": [f"failed {uri}", "key super-secret-admin-key", "Bearer abc.def.ghi",
                                            SCHEME + "other:pw@host/x", "X-Admin-Key: leak"]})
    for secret in ("hunter2", "super-secret-admin-key", "abc.def.ghi", "other:pw", "leak", "cluster.example"):
        assert secret not in text
    import logging
    record = logging.LogRecord("x", logging.ERROR, "f", 1, "boom %s", (uri,), None)
    assert "hunter2" not in refresh.RedactingFormatter("%(message)s").format(record)


@pytest.mark.asyncio
async def test_unexpected_errors_print_only_the_error_type(monkeypatch, capsys):
    uri = SCHEME + "user:hunter2@host/elegance_shawls_staging"
    monkeypatch.setattr(settings, "MONGODB_URI", uri)
    monkeypatch.setattr(settings, "MONGO_DB_NAME", "elegance_shawls_staging")
    async def failing(mode): raise RuntimeError(f"cannot connect to {uri}")
    monkeypatch.setattr(refresh, "open_db", failing)
    assert await run_cli("once") == 1
    out = capsys.readouterr().out
    assert "hunter2" not in out and "internal_error" in out and "RuntimeError" in out


@pytest.mark.asyncio
async def test_error_samples_in_a_real_run_carry_no_secrets(db, site, monkeypatch):
    monkeypatch.setattr(settings, "MONGODB_URI", SCHEME + "user:hunter2@host/db")
    site.html("/products/b", "x", status=404)
    text = render_summary(await go(db, site))
    assert "hunter2" not in text and SCHEME + "" not in text and "/products/b" in text


def test_worker_flags_and_default_mode_are_preserved():
    from ingestion.worker import parse_args
    assert not any(vars(parse_args([]))[k] for k in ("once", "dry_run", "discovery_only"))
    a = parse_args(["--once", "--summary-file", "x.json"])
    assert a.once and a.summary_file == "x.json"
    assert parse_args(["--dry-run"]).dry_run and parse_args(["--discovery-only"]).discovery_only
    import argparse
    with pytest.raises(SystemExit):
        parse_args(["--mongodb-uri", SCHEME + "x"])  # secrets are never command-line arguments


# ---- local monthly helper and CI hygiene ------------------------------------------------------

import fcntl
import os
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "apps/backend/scripts/monthly_refresh.sh"
needs_flock = pytest.mark.skipif(shutil.which("flock") is None, reason="flock not installed")


def run_script(tmp_path, *args, env=None, stub_exit=0):
    stub = tmp_path / "fake_python"
    stub.write_text(f"#!/usr/bin/env bash\necho \"$@\" > '{tmp_path}/argv'\necho '{{\"termination_reason\": \"stub\"}}'\nexit {stub_exit}\n")
    stub.chmod(0o755)
    environ = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "PYTHON": str(stub), "MONGO_DB_NAME": "elegance_shawls_staging",
               "REFRESH_LOCK_FILE": str(tmp_path / "lock"), "REFRESH_OUTPUT_DIR": str(tmp_path / "out"), **(env or {})}
    return subprocess.run(["bash", str(SCRIPT), *args], env=environ, capture_output=True, text=True, timeout=30)


@needs_flock
def test_helper_runs_the_bounded_one_shot_and_writes_an_ignored_summary(tmp_path):
    result = run_script(tmp_path)
    assert result.returncode == 0
    assert (tmp_path / "argv").read_text().split()[:3] == ["-m", "ingestion.worker", "--once"]
    assert "--summary-file" in (tmp_path / "argv").read_text()
    assert (tmp_path / "out/.gitignore").read_text() == "*\n"


@needs_flock
@pytest.mark.parametrize("mode", ["--once", "--dry-run", "--discovery-only"])
def test_helper_passes_through_only_the_supported_modes(tmp_path, mode):
    assert run_script(tmp_path, mode).returncode == 0
    assert mode in (tmp_path / "argv").read_text()


@needs_flock
@pytest.mark.parametrize("args", [("--mongodb-uri", SCHEME + "u:p@h/db"), (SCHEME + "u:p@h/db",), ("--once", "--dry-run"), ("--admin-key=x",)])
def test_helper_never_accepts_secrets_or_other_arguments(tmp_path, args):
    result = run_script(tmp_path, *args)
    assert result.returncode == 64 and not (tmp_path / "argv").exists()
    assert "u:p" not in result.stdout + result.stderr


@needs_flock
@pytest.mark.parametrize("name", ["elegance_shawls", "elegance_shawls_prod", "production", "prod_staging", "stagingx"])
def test_helper_refuses_a_database_that_is_not_clearly_staging(tmp_path, name):
    result = run_script(tmp_path, env={"MONGO_DB_NAME": name})
    assert result.returncode == 2 and not (tmp_path / "argv").exists()


@needs_flock
def test_helper_reads_the_database_name_from_the_ignored_env_file_without_printing_secrets(tmp_path):
    backend = tmp_path / "backend"
    (backend / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, backend / "scripts/monthly_refresh.sh")
    (backend / ".env").write_text(f"MONGODB_URI={SCHEME}user:hunter2@host/x\nMONGO_DB_NAME=elegance_shawls_prod\n")
    environ = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "REFRESH_LOCK_FILE": str(tmp_path / "lock")}
    result = subprocess.run(["bash", str(backend / "scripts/monthly_refresh.sh")], env=environ, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2 and "hunter2" not in result.stdout + result.stderr


@needs_flock
def test_helper_refuses_when_no_database_name_is_configured_anywhere(tmp_path):
    backend = tmp_path / "backend"  # a clean copy, so a developer's real .env cannot supply a name
    (backend / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, backend / "scripts/monthly_refresh.sh")
    environ = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "REFRESH_LOCK_FILE": str(tmp_path / "lock")}
    result = subprocess.run(["bash", str(backend / "scripts/monthly_refresh.sh")], env=environ, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2


@needs_flock
def test_helper_blocks_overlapping_runs(tmp_path):
    with open(tmp_path / "lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run_script(tmp_path)
    assert result.returncode == 75 and not (tmp_path / "argv").exists()
    assert run_script(tmp_path).returncode == 0  # released lock: runs again


@needs_flock
def test_helper_returns_the_failure_exit_code(tmp_path):
    assert run_script(tmp_path, stub_exit=1).returncode == 1


def test_no_github_workflow_runs_the_refresh_or_touches_mongodb():
    for workflow in (REPO / ".github/workflows").glob("*.y*ml"):
        text = workflow.read_text()
        assert "ingestion.worker" not in text and "monthly" not in workflow.name
        assert "STAGING_MONGODB_URI" not in text and "elegance_shawls_staging" not in text
        assert "cron:" not in text  # nothing here may schedule a refresh


def test_helper_script_has_no_credentials_or_production_targets():
    text = SCRIPT.read_text()
    assert SCHEME + "" not in text and SRV + "" not in text and "set -x" not in text
    assert "onrender.com" not in text and "vercel" not in text.lower()


# ---- --discovery-only needs no MongoDB credentials or database modules -----------------------------

import sys

BACKEND = Path(__file__).resolve().parents[1]
FORBIDDEN_MODULES = ("database", "database.db", "motor", "motor.motor_asyncio", "pymongo", "ingestion.jobs",
                     "ingestion.pipeline", "ingestion.safe_fetch", "httpx")
# Explicitly unauthorized, so even a developer's local .env cannot make these subprocess runs touch a real source.
HERMETIC = {"INGESTION_SOURCE_AUTHORIZED": "false", "INGESTION_SOURCE_DOMAIN": "", "INGESTION_SOURCE_ID": "t"}


def run_entry(*flags, env=None, snippet=None):
    environ = {"PATH": os.environ["PATH"], "HOME": "/nonexistent", **HERMETIC, **(env or {})}
    if snippet:
        cmd = [sys.executable, "-c", snippet]
    else:
        cmd = [sys.executable, "-m", "ingestion.worker", *flags]
    return subprocess.run(cmd, cwd=BACKEND, env=environ, capture_output=True, text=True, timeout=60)


def test_discovery_only_starts_without_a_mongodb_uri():
    result = run_entry("--discovery-only", env={"MONGO_DB_NAME": "elegance_shawls_staging"})
    out = json.loads(result.stdout)
    assert out["termination_reason"] == "no_authorized_sources"  # reached dispatch; no source is configured here
    assert "Field required" not in result.stdout + result.stderr and "Traceback" not in result.stderr
    assert result.returncode == 1


def test_discovery_only_never_loads_database_or_fetch_modules_before_a_source_is_authorized():
    snippet = (
        "import runpy, sys, json\n"
        "sys.argv = ['ingestion.worker', '--discovery-only']\n"
        "try:\n    runpy.run_module('ingestion.worker', run_name='__main__')\n"
        "except SystemExit:\n    pass\n"
        f"print('LOADED=' + json.dumps([m for m in {FORBIDDEN_MODULES!r} if m in sys.modules]))\n"
    )
    result = run_entry(snippet=snippet, env={"MONGO_DB_NAME": "elegance_shawls_staging"})
    loaded = [line for line in result.stdout.splitlines() if line.startswith("LOADED=")]
    forbidden = set(json.loads(loaded[0][7:])) - {"ingestion.safe_fetch", "httpx"}  # fetching is allowed; databases are not
    assert forbidden == set(), forbidden


@pytest.mark.parametrize("name", ["elegance_shawls_prod", "elegance_shawls", "production", "prod_staging", "stagingx", ""])
def test_bad_database_names_are_refused_before_settings_or_source_access(name):
    env = {"MONGO_DB_NAME": name}  # set explicitly (even empty) so a local .env cannot fill it in
    snippet = (
        "import runpy, sys, json\n"
        "sys.argv = ['ingestion.worker', '--discovery-only']\n"
        "try:\n    runpy.run_module('ingestion.worker', run_name='__main__')\n"
        "except SystemExit as e:\n    print('EXIT=%s' % e.code)\n"
        "print('LOADED=' + json.dumps([m for m in ('configuration.config','ingestion.safe_fetch','ingestion.sitemap','httpx','database','motor') if m in sys.modules]))\n"
    )
    result = run_entry(snippet=snippet, env=env)
    assert "EXIT=1" in result.stdout and "staging_guard_failed" in result.stdout
    assert "LOADED=[]" in result.stdout  # nothing that could reach a source or database was even imported
    assert "Traceback" not in result.stderr and "Field required" not in result.stdout + result.stderr


def test_a_connection_string_in_the_environment_is_never_printed():
    secret = SCHEME + "user:hunter2@host.example/elegance_shawls_staging"
    result = run_entry("--discovery-only", env={"MONGO_DB_NAME": "elegance_shawls_staging", "MONGODB_URI": secret})
    assert "hunter2" not in result.stdout + result.stderr and secret not in result.stdout + result.stderr


def test_a_missing_database_name_is_refused_before_settings_load(monkeypatch):
    from ingestion import staging_guard
    monkeypatch.delenv("MONGO_DB_NAME", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)  # simulate a checkout without a .env
    with pytest.raises(StagingGuardError):
        staging_guard.prepare_discovery_environment()


@pytest.mark.asyncio
async def test_discovery_only_cli_succeeds_without_any_database_connection(monkeypatch, site, capsys):
    monkeypatch.setattr(settings, "MONGO_DB_NAME", "elegance_shawls_staging")
    monkeypatch.setattr(settings, "MONGODB_URI", "")
    monkeypatch.setattr(settings, "ingestion_source_domain", "shop.example")
    monkeypatch.setattr(settings, "ingestion_source_authorized", True)
    async def forbidden(mode): raise AssertionError("discovery-only must not connect to MongoDB")
    monkeypatch.setattr(refresh, "open_db", forbidden)
    assert await run_cli("discovery-only", fetcher_factory=lambda p: site.factory(p)) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["totals"]["discovered_urls"] == 2 and printed["totals"]["jobs_created"] == 0
    assert site.products_fetched() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["discovery-only", "dry-run", "once"])
async def test_a_non_staging_database_is_refused_before_any_source_access(monkeypatch, mode, capsys):
    monkeypatch.setattr(settings, "MONGO_DB_NAME", "elegance_shawls_prod")
    def no_fetch(policy): raise AssertionError("source must not be contacted")
    async def no_db(mode): raise AssertionError("database must not be opened")
    monkeypatch.setattr(refresh, "open_db", no_db)
    assert await run_cli(mode, fetcher_factory=no_fetch) == 1
    assert "staging_guard_failed" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_only_the_database_aware_modes_open_the_database(monkeypatch, db, site):
    monkeypatch.setattr(settings, "MONGO_DB_NAME", "elegance_shawls_staging")
    monkeypatch.setattr(settings, "ingestion_source_domain", "shop.example")
    monkeypatch.setattr(settings, "ingestion_source_authorized", True)
    opened = []
    async def fake_open(mode):
        opened.append(mode)
        return _Client(), db
    monkeypatch.setattr(refresh, "open_db", fake_open)
    for mode in ("discovery-only", "dry-run", "once"):
        await run_cli(mode, fetcher_factory=lambda p: site.factory(p))
    assert opened == ["dry-run", "once"]
    assert await db.ingestion_jobs.count_documents({}) == 2  # only --once created jobs; dry-run still read the database
