"""PKR reference conversion: mocked rate API only, suggestion-only behaviour."""
import httpx
import pytest

from ingestion import fx
from ingestion.fx import Rate, RateUnavailable, get_pkr_rate, parse_rate, suggest_pkr
from routes import ingestion_routes

GOOD = {"date": "2026-10-28", "aud": {"pkr": 194.5, "usd": 0.65}}


@pytest.fixture(autouse=True)
def clear_cache():
    fx._cache.clear()
    yield
    fx._cache.clear()


def factory(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_rate_is_fetched_from_the_fixed_hosts_and_cached():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=GOOD)

    rate = await get_pkr_rate("AUD", client_factory=factory(handler))
    again = await get_pkr_rate("aud", client_factory=factory(handler))
    assert rate == again == Rate("aud", 194.5, "2026-10-28")
    assert seen == ["https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/aud.json"]  # one call


@pytest.mark.asyncio
async def test_falls_back_to_the_second_host():
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(503) if request.url.host == "cdn.jsdelivr.net" else httpx.Response(200, json=GOOD)

    assert (await get_pkr_rate("aud", client_factory=factory(handler))).rate == 194.5
    assert seen == ["cdn.jsdelivr.net", "latest.currency-api.pages.dev"]


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["", "us", "usdx", "../x", "a/b", "aud.json?x=", "12$", "AU D"])
async def test_only_three_letter_codes_reach_the_network(code):
    def handler(request):
        raise AssertionError("must not call the network")
    with pytest.raises(RateUnavailable):
        await get_pkr_rate(code, client_factory=factory(handler))


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    httpx.Response(200, json={"date": "2026-10-28", "aud": {"pkr": -1}}),
    httpx.Response(200, json={"date": "2026-10-28", "aud": {"pkr": "194"}}),
    httpx.Response(200, json={"date": "2026-10-28", "aud": {"pkr": 1e12}}),
    httpx.Response(200, json={"date": "today", "aud": {"pkr": 194}}),
    httpx.Response(200, json={"date": "2026-10-28", "aud": {}}),
    httpx.Response(200, json=[1, 2]),
    httpx.Response(200, text="not json"),
    httpx.Response(302, headers={"location": "https://evil.example/x"}),
    httpx.Response(404),
])
async def test_bad_or_hostile_responses_are_rejected(response):
    with pytest.raises(RateUnavailable):
        await get_pkr_rate("aud", client_factory=factory(lambda r: response))


@pytest.mark.asyncio
async def test_network_failure_is_reported_not_raised_raw():
    def handler(request):
        raise httpx.ConnectTimeout("t")
    with pytest.raises(RateUnavailable):
        await get_pkr_rate("aud", client_factory=factory(handler))


def test_parse_and_round():
    assert suggest_pkr(125.0, Rate("aud", 194.9163, "2026-10-28")) == 24365
    assert parse_rate("aud", GOOD).rate == 194.5


def test_ingestion_code_never_uses_exchange_rates():
    from pathlib import Path
    root = Path(ingestion_routes.__file__).parents[1] / "ingestion"
    for name in ("pipeline.py", "normalize.py", "refresh.py", "worker.py", "sitemap.py"):
        assert "fx" not in (root / name).read_text().replace("fixture", "")
