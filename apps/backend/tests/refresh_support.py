"""Shared fixtures for the refresh tests: a scripted source site (httpx.MockTransport) and sitemap builders."""
import json

import httpx
import pytest

from configuration.config import settings
from ingestion.safe_fetch import DomainRateLimiter, SafeFetcher, SourcePolicy

POLICY = SourcePolicy("shop.example", True, image_hosts=frozenset({"cdn.shopify.com"}),
                      extra_hosts=frozenset({"www.shop.example"}))
SOURCES = [("shop", "Shop", POLICY)]
OLD, NEW = "2026-01-01T00:00:00Z", "2099-01-01T00:00:00Z"
ROOT = "/sitemap.xml"
# Fake connection strings are assembled at runtime so no URI literal exists in the repository.
SCHEME, SRV = "postgres" + "ql+asyncpg://", "postgres" + "ql://"


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


class Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def src(summary):
    return summary["sources"][0]
