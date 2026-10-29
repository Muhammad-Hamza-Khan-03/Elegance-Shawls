"""Sitemap discovery for the one-shot refresh.

Every sitemap and every URL inside one must pass the same source policy as a product fetch.
A URL on a host that is not approved is a policy violation and stops the source; a URL on an
approved host that is not ``/products/<handle>`` is simply ignored. Remote XML is untrusted:
DTDs and entities are rejected before parsing and responses are size-capped by the fetcher.
"""
import asyncio
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

from configuration.config import settings
from ingestion.normalize import PATH_PATTERN
from ingestion.safe_fetch import SITEMAP_CONTENT_TYPES, FetchError, SafeFetcher, SourcePolicy, UnsafeURL, validate_url

MAX_SITEMAP_DEPTH = 2
_DTD = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.I)


class DiscoveryError(Exception):
    """A source-level failure with a stable machine-readable ``code``."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


@dataclass
class Discovery:
    products: dict[str, datetime | None] = field(default_factory=dict)  # path -> newest lastmod
    duplicates: int = 0
    ignored: int = 0
    sitemaps_fetched: int = 0


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_lastmod(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_sitemap(text: str) -> tuple[str, list[tuple[str, str | None]]]:
    """-> ("index" | "urlset", [(loc, lastmod)])."""
    if _DTD.search(text):
        raise DiscoveryError("sitemap_invalid", "Sitemap contains a DTD or entity declaration")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise DiscoveryError("sitemap_invalid", "Sitemap is not valid XML") from exc
    kind = {"sitemapindex": "index", "urlset": "urlset"}.get(_local(root.tag))
    if not kind:
        raise DiscoveryError("sitemap_invalid", "Unexpected sitemap root element")
    entries = []
    for child in root:
        values = {_local(el.tag): (el.text or "").strip() for el in child if isinstance(el.tag, str)}
        if values.get("loc"):
            entries.append((values["loc"], values.get("lastmod") or None))
    return kind, entries


def canonical_product_path(loc: str, policy: SourcePolicy) -> str | None:
    """Product path for an approved-host URL, None for other pages. Raises UnsafeURL off-policy."""
    parts = urlsplit(loc.strip())
    validate_url(parts._replace(query="", fragment="").geturl(), policy)
    path = parts.path.rstrip("/")
    return path if PATH_PATTERN.fullmatch(path) else None


async def _fetch_sitemap(fetcher: SafeFetcher, url: str, sleep) -> str:
    attempts = max(settings.ingestion_job_max_attempts, 1)
    for attempt in range(1, attempts + 1):
        try:
            return (await fetcher.fetch(url, content_types=SITEMAP_CONTENT_TYPES)).text
        except UnsafeURL as exc:
            raise DiscoveryError("source_policy_violation", str(exc)) from exc
        except FetchError as exc:
            if exc.retryable and attempt < attempts:
                await sleep(settings.ingestion_job_backoff_seconds * 2 ** (attempt - 1))
                continue
            raise DiscoveryError("sitemap_unavailable", f"Sitemap could not be fetched: {exc}") from exc
    raise DiscoveryError("sitemap_unavailable")  # pragma: no cover


async def discover_products(
    fetcher: SafeFetcher, policy: SourcePolicy, *, max_urls: int | None = None,
    max_sitemaps: int | None = None, sleep=asyncio.sleep,
) -> Discovery:
    max_urls = settings.ingestion_max_urls_per_source if max_urls is None else max_urls
    max_sitemaps = settings.ingestion_max_sitemaps if max_sitemaps is None else max_sitemaps
    root = f"https://{policy.domain}{settings.ingestion_sitemap_path}"
    result, seen = Discovery(), set()
    queue = [(root, 0)]
    while queue:
        url, depth = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if len(seen) > max_sitemaps:
            raise DiscoveryError("too_many_sitemaps", f"More than {max_sitemaps} sitemaps")
        kind, entries = parse_sitemap(await _fetch_sitemap(fetcher, url, sleep))
        result.sitemaps_fetched += 1
        for loc, lastmod in entries:
            try:
                if kind == "index":
                    validate_url(loc, policy)
                    if depth + 1 > MAX_SITEMAP_DEPTH:
                        raise DiscoveryError("sitemap_invalid", "Sitemap index nesting is too deep")
                    # Only product sitemaps are followed; pages, collections and blogs are ignored.
                    if "product" in urlsplit(loc).path.lower():
                        queue.append((loc, depth + 1))
                    else:
                        result.ignored += 1
                    continue
                path = canonical_product_path(loc, policy)
            except UnsafeURL as exc:
                raise DiscoveryError("source_policy_violation", f"Sitemap lists a disallowed URL: {exc}") from exc
            if path is None:
                result.ignored += 1
                continue
            when = parse_lastmod(lastmod)
            if path in result.products:
                result.duplicates += 1
                known = result.products[path]
                result.products[path] = max((d for d in (known, when) if d), default=None)
                continue
            if len(result.products) >= max_urls:
                raise DiscoveryError("discovery_limit_exceeded", f"More than {max_urls} product URLs")
            result.products[path] = when
    if not result.products:
        raise DiscoveryError("sitemap_empty", "Sitemap listed no product URLs")
    return result
