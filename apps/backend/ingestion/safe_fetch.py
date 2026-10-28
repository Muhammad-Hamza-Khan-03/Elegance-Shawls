"""Guarded HTTP fetching for untrusted remote pages.

Every hop (including redirects) is checked against the source allowlist, DNS is resolved
once, every resolved address must be public, and the TCP connection is pinned to the
validated address so a second DNS answer cannot redirect us to an internal host.
"""
import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable
from urllib.parse import urljoin, urlsplit

import httpx

from configuration.config import settings

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "application/json")
# Not globally routable on every provider, but listed explicitly so intent is obvious.
METADATA_ADDRESSES = {ipaddress.ip_address("169.254.169.254"), ipaddress.ip_address("fd00:ec2::254")}


class FetchError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class UnsafeURL(FetchError):
    """Rejected by policy; retrying cannot help."""


class ResponseTooLarge(FetchError):
    pass


def _host_set(raw: str) -> frozenset[str]:
    return frozenset(h.strip().lower().rstrip(".") for h in raw.split(",") if h.strip())


@dataclass(frozen=True)
class SourcePolicy:
    """``domain`` is the canonical host (used to build URLs); ``extra_hosts`` are other exact
    hosts of the same source. Nothing else, including subdomains, is ever allowed."""
    domain: str
    authorized: bool
    image_hosts: frozenset[str] = field(default_factory=frozenset)
    extra_hosts: frozenset[str] = field(default_factory=frozenset)

    @property
    def hosts(self) -> frozenset[str]:
        return frozenset({self.domain, *self.extra_hosts}) - {""}

    @classmethod
    def from_settings(cls) -> "SourcePolicy":
        return cls(
            domain=settings.ingestion_source_domain.strip().lower().rstrip("."),
            authorized=settings.ingestion_source_authorized,
            image_hosts=_host_set(settings.ingestion_image_hosts),
            extra_hosts=_host_set(settings.ingestion_allowed_hosts),
        )


def validate_url(url: str, policy: SourcePolicy) -> str:
    """Return the hostname if the URL is allowed, otherwise raise UnsafeURL."""
    if not policy.domain or not policy.authorized:
        raise UnsafeURL("No authorized ingestion source is configured")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeURL("Malformed URL") from exc
    if parts.scheme != "https":
        raise UnsafeURL("Only https URLs are allowed")
    if parts.username is not None or parts.password is not None:
        raise UnsafeURL("Credentials in URLs are not allowed")
    if port not in (None, 443):
        raise UnsafeURL("Non-standard ports are not allowed")
    host = (parts.hostname or "").lower().rstrip(".")
    if host not in policy.hosts:
        raise UnsafeURL("Host is not on the source allowlist")
    return host


def is_allowed_image_url(url: str, policy: SourcePolicy) -> bool:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").lower().rstrip(".")
    return (
        parts.scheme == "https"
        and parts.username is None
        and port in (None, 443)
        and host in (policy.hosts | policy.image_hosts)
    )


def is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip in METADATA_ADDRESSES:
        return False
    return ip.is_global and not ip.is_multicast


Resolver = Callable[[str], Awaitable[list[str]]]


async def system_resolver(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"DNS resolution failed: {exc}", retryable=True) from exc
    return sorted({info[4][0] for info in infos})


async def resolve_public(host: str, resolver: Resolver) -> str:
    addresses = await resolver(host)
    if not addresses:
        raise FetchError("Host did not resolve", retryable=True)
    # One private answer taints the host: refuse rather than hope we pick the public one.
    if not all(is_public_address(a) for a in addresses):
        raise UnsafeURL("Host resolves to a non-public address")
    return addresses[0]


class DomainRateLimiter:
    """Minimum spacing between requests to the same domain, within this process."""

    def __init__(self, min_interval: float, clock=time.monotonic, sleep=asyncio.sleep):
        self.min_interval = min_interval
        self._clock, self._sleep = clock, sleep
        self._next_allowed: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def wait(self, domain: str) -> None:
        async with self._lock:
            now = self._clock()
            ready = self._next_allowed.get(domain, now)
            self._next_allowed[domain] = max(ready, now) + self.min_interval
        if ready > now:
            await self._sleep(ready - now)


ClientFactory = Callable[[], httpx.AsyncClient]


def default_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        follow_redirects=False,
        trust_env=False,  # ignore proxy env vars that would bypass IP pinning
        timeout=httpx.Timeout(
            connect=settings.ingestion_connect_timeout_seconds,
            read=settings.ingestion_read_timeout_seconds,
            write=settings.ingestion_read_timeout_seconds,
            pool=settings.ingestion_connect_timeout_seconds,
        ),
    )


@dataclass
class FetchedPage:
    url: str
    status: int
    text: str


class SafeFetcher:
    def __init__(
        self,
        policy: SourcePolicy | None = None,
        *,
        resolver: Resolver = system_resolver,
        client_factory: ClientFactory = default_client,
        rate_limiter: DomainRateLimiter | None = None,
        max_bytes: int | None = None,
        max_redirects: int | None = None,
    ):
        self.policy = policy or SourcePolicy.from_settings()
        self.resolver = resolver
        self.client_factory = client_factory
        self.rate_limiter = rate_limiter or DomainRateLimiter(settings.ingestion_domain_min_interval_seconds)
        self.max_bytes = max_bytes or settings.ingestion_max_response_bytes
        self.max_redirects = settings.ingestion_max_redirects if max_redirects is None else max_redirects

    async def fetch(self, url: str) -> FetchedPage:
        current = url
        async with self.client_factory() as client:
            for _ in range(self.max_redirects + 1):
                host = validate_url(current, self.policy)
                address = await resolve_public(host, self.resolver)
                # One bucket per source, so hopping between its hosts cannot sidestep the spacing.
                await self.rate_limiter.wait(self.policy.domain)
                response_url, status, location, body = await self._get_once(client, current, host, address)
                if status in REDIRECT_STATUSES:
                    if not location:
                        raise FetchError("Redirect without Location")
                    current = urljoin(current, location)
                    continue
                if status == 429 or status >= 500:
                    raise FetchError(f"Source returned HTTP {status}", retryable=True)
                if status >= 400:
                    raise FetchError(f"Source returned HTTP {status}")
                return FetchedPage(url=response_url, status=status, text=body)
        raise FetchError("Too many redirects")

    async def _get_once(self, client, url: str, host: str, address: str):
        parts = urlsplit(url)
        literal = f"[{address}]" if ":" in address else address
        pinned = parts._replace(netloc=literal).geturl()
        request = client.build_request(
            "GET", pinned,
            headers={"Host": host, "Accept": "text/html,application/json;q=0.9", "User-Agent": "EleganceIngestion/1.0"},
            extensions={"sni_hostname": host},
        )
        try:
            response = await client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise FetchError("Request timed out", retryable=True) from exc
        except httpx.TransportError as exc:
            raise FetchError(f"Connection failed: {type(exc).__name__}", retryable=True) from exc
        try:
            if response.status_code in REDIRECT_STATUSES or response.status_code >= 400:
                return url, response.status_code, response.headers.get("location"), ""
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type not in ALLOWED_CONTENT_TYPES:
                raise FetchError(f"Unsupported content type: {content_type or 'missing'}")
            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > self.max_bytes:
                raise ResponseTooLarge("Response exceeds size limit")
            chunks, total = [], 0
            try:
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise ResponseTooLarge("Response exceeds size limit")
                    chunks.append(chunk)
            except httpx.TimeoutException as exc:
                raise FetchError("Read timed out", retryable=True) from exc
            except httpx.TransportError as exc:
                raise FetchError(f"Read failed: {type(exc).__name__}", retryable=True) from exc
            return url, response.status_code, None, b"".join(chunks).decode("utf-8", errors="replace")
        finally:
            await response.aclose()
