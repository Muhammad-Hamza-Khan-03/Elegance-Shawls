import httpx
import pytest

from ingestion.safe_fetch import (
    DomainRateLimiter, FetchError, ResponseTooLarge, SafeFetcher, SourcePolicy, UnsafeURL,
    is_allowed_image_url, is_public_address, validate_url,
)

POLICY = SourcePolicy(domain="shop.example", authorized=True, image_hosts=frozenset({"cdn.example"}))
PAGE = "https://shop.example/products/a"


async def public_dns(host):
    return ["93.184.216.34"]


def fetcher(handler, resolver=public_dns, policy=POLICY, **kw):
    return SafeFetcher(
        policy, resolver=resolver,
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        rate_limiter=DomainRateLimiter(0), **kw,
    )


def html(_request):
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="<html>ok</html>")


@pytest.mark.asyncio
async def test_fetches_allowed_page_pinned_to_resolved_ip():
    seen = []

    def handler(request):
        seen.append((request.url.host, request.headers["host"]))
        return html(request)

    page = await fetcher(handler).fetch(PAGE)
    assert page.text == "<html>ok</html>"
    assert seen == [("93.184.216.34", "shop.example")]


@pytest.mark.parametrize("url", [
    "http://shop.example/products/a",
    "https://evil.example/products/a",
    "https://shop.example.evil.example/products/a",
    "https://user:pw@shop.example/products/a",
    "https://shop.example:8443/products/a",
    "https://127.0.0.1/products/a",
    "ftp://shop.example/x",
    "https://shop.example:abc/x",
])
def test_unlisted_or_unsafe_urls_rejected(url):
    with pytest.raises(UnsafeURL):
        validate_url(url, POLICY)


def test_unauthorized_or_unconfigured_source_rejected():
    with pytest.raises(UnsafeURL):
        validate_url(PAGE, SourcePolicy(domain="shop.example", authorized=False))
    with pytest.raises(UnsafeURL):
        validate_url(PAGE, SourcePolicy(domain="", authorized=True))


def test_validate_returns_normalized_host():
    assert validate_url("https://SHOP.example./products/a", POLICY) == "shop.example"


@pytest.mark.parametrize("address", [
    "10.0.0.5", "172.16.0.1", "192.168.1.1", "127.0.0.1", "169.254.169.254", "169.254.1.1",
    "0.0.0.0", "100.64.0.1", "224.0.0.1", "::1", "fe80::1", "fc00::1", "fd00:ec2::254",
    "::ffff:127.0.0.1", "::ffff:169.254.169.254", "not-an-ip",
])
def test_non_public_addresses_rejected(address):
    assert not is_public_address(address)


def test_public_addresses_accepted():
    assert is_public_address("93.184.216.34")
    assert is_public_address("2606:2800:220:1:248:1893:25c8:1946")


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["10.0.0.5", "127.0.0.1", "169.254.169.254", "::1"])
async def test_host_resolving_to_private_address_is_blocked_before_any_request(address):
    async def dns(_):
        return [address]

    def handler(request):
        raise AssertionError("no request should be sent")

    with pytest.raises(UnsafeURL):
        await fetcher(handler, resolver=dns).fetch(PAGE)


@pytest.mark.asyncio
async def test_one_private_answer_among_public_ones_is_blocked():
    async def dns(_):
        return ["93.184.216.34", "10.0.0.1"]

    with pytest.raises(UnsafeURL):
        await fetcher(html, resolver=dns).fetch(PAGE)


@pytest.mark.asyncio
async def test_redirect_within_allowlist_is_followed():
    def handler(request):
        if request.url.path == "/products/a":
            return httpx.Response(301, headers={"location": "/products/b"})
        return html(request)

    assert (await fetcher(handler).fetch(PAGE)).text == "<html>ok</html>"


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [
    "https://evil.example/x", "http://shop.example/x", "https://169.254.169.254/latest/meta-data/",
    "https://127.0.0.1/admin",
])
async def test_redirect_to_disallowed_target_is_rejected(target):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": target})

    with pytest.raises(UnsafeURL):
        await fetcher(handler).fetch(PAGE)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_redirect_loop_is_bounded():
    def handler(request):
        return httpx.Response(302, headers={"location": "/products/a"})

    with pytest.raises(FetchError, match="Too many redirects"):
        await fetcher(handler, max_redirects=3).fetch(PAGE)


@pytest.mark.asyncio
async def test_redirect_to_host_resolving_privately_is_blocked():
    policy = SourcePolicy(domain="shop.example", authorized=True)
    # Same-host redirect re-resolves; a rebinding answer on the second lookup is caught.
    answers = iter([["93.184.216.34"], ["10.0.0.1"]])

    async def rebinding(_):
        return next(answers)

    def handler(request):
        return httpx.Response(302, headers={"location": "/products/b"})

    with pytest.raises(UnsafeURL):
        await fetcher(handler, resolver=rebinding, policy=policy).fetch(PAGE)


@pytest.mark.asyncio
async def test_declared_oversize_response_rejected():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html", "content-length": "5000"}, content=b"x" * 5000)

    with pytest.raises(ResponseTooLarge):
        await fetcher(handler, max_bytes=1000).fetch(PAGE)


@pytest.mark.asyncio
async def test_streamed_oversize_response_rejected_without_content_length():
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(50):
                yield b"x" * 100

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, stream=Stream())

    with pytest.raises(ResponseTooLarge):
        await fetcher(handler, max_bytes=1000).fetch(PAGE)


@pytest.mark.asyncio
async def test_unsupported_content_type_rejected():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/octet-stream"}, content=b"zz")

    with pytest.raises(FetchError, match="content type"):
        await fetcher(handler).fetch(PAGE)


@pytest.mark.asyncio
async def test_timeout_is_retryable():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(FetchError) as info:
        await fetcher(handler).fetch(PAGE)
    assert info.value.retryable


@pytest.mark.asyncio
@pytest.mark.parametrize("status,retryable", [(500, True), (503, True), (429, True), (404, False), (403, False)])
async def test_http_errors_classified(status, retryable):
    def handler(request):
        return httpx.Response(status)

    with pytest.raises(FetchError) as info:
        await fetcher(handler).fetch(PAGE)
    assert info.value.retryable is retryable


@pytest.mark.asyncio
async def test_rate_limiter_spaces_requests_per_domain():
    now = [0.0]
    slept = []

    async def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    limiter = DomainRateLimiter(2.0, clock=lambda: now[0], sleep=sleep)
    await limiter.wait("shop.example")
    await limiter.wait("shop.example")
    await limiter.wait("other.example")
    assert slept == [2.0]


def test_image_urls_limited_to_https_allowed_hosts():
    assert is_allowed_image_url("https://shop.example/cdn/a.jpg", POLICY)
    assert is_allowed_image_url("https://cdn.example/a.jpg", POLICY)
    assert not is_allowed_image_url("http://cdn.example/a.jpg", POLICY)
    assert not is_allowed_image_url("https://evil.example/a.jpg", POLICY)
    assert not is_allowed_image_url("https://169.254.169.254/a.jpg", POLICY)
    assert not is_allowed_image_url("javascript:alert(1)", POLICY)
