"""Reference PKR conversion for the review screen.

Rates come from the free, keyless fawazahmed0 currency API. The result is only ever a
suggestion shown to a reviewer: it is not stored, not applied to a price and never used by
ingestion. Both rate hosts are fixed constants; only a validated 3-letter code is substituted.
"""
import math
import re
import time
from dataclasses import dataclass

import httpx

RATE_URLS = (
    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{code}.json",
    "https://latest.currency-api.pages.dev/v1/currencies/{code}.json",
)
CODE = re.compile(r"^[a-z]{3}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_BYTES = 500_000
CACHE_SECONDS = 6 * 3600
TARGET = "pkr"


class RateUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Rate:
    code: str
    rate: float
    date: str


_cache: dict[str, tuple[float, Rate]] = {}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=httpx.Timeout(5.0))


def parse_rate(code: str, payload) -> Rate:
    try:
        rate = payload[code][TARGET]
        date = payload["date"]
    except (KeyError, TypeError) as exc:
        raise RateUnavailable("Unexpected rate response") from exc
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or not 0 < rate < 1e7:
        raise RateUnavailable("Implausible rate")
    if not isinstance(date, str) or not DATE.fullmatch(date):
        raise RateUnavailable("Unexpected rate date")
    return Rate(code=code, rate=float(rate), date=date)


async def get_pkr_rate(currency: str, *, client_factory=_client, clock=time.monotonic) -> Rate:
    code = (currency or "").strip().lower()
    if not CODE.fullmatch(code):
        raise RateUnavailable("Unsupported currency code")
    if code == TARGET:
        return Rate(code=code, rate=1.0, date=time.strftime("%Y-%m-%d", time.gmtime()))
    cached = _cache.get(code)
    if cached and clock() - cached[0] < CACHE_SECONDS:
        return cached[1]
    async with client_factory() as client:
        for template in RATE_URLS:
            try:
                response = await client.get(template.format(code=code), headers={"Accept": "application/json"})
                if response.status_code != 200 or len(response.content) > MAX_BYTES:
                    continue
                rate = parse_rate(code, response.json())
            except (httpx.HTTPError, ValueError, RateUnavailable):
                continue
            _cache[code] = (clock(), rate)
            return rate
    raise RateUnavailable("Exchange rate is currently unavailable")


def suggest_pkr(price: float, rate: Rate) -> int:
    return int(round(price * rate.rate))
