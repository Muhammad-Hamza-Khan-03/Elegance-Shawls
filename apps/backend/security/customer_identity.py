"""Provider-neutral verification of an external identity token (an OIDC-style RS256 JWT), M4 customer authentication.

Stdlib only: the project does not depend on a JWT or crypto library, and verifying RS256 needs just the public key (modular
exponentiation plus an exact re-encoding of the PKCS#1 v1.5 block, so there is no padding parser to fool). Everything is
strict and fails closed: one algorithm (RS256), mandatory kid/iss/aud/exp/sub, exact issuer and audience, bounded clock leeway,
and no header that could redirect key lookup (jku, x5u, jwk, crit). A token is only a way to learn (issuer, subject); the caller
decides what that identity maps to.

`JwksCache` is the bounded key source: one single-flight refresh at a time, never more often than `min_refresh_interval` (failed
attempts count, and a forged `kid` cannot force a fetch), whole-document replacement so rotated-out keys disappear, a hard stale
ceiling after which verification is unavailable, and a cap on document size, key count and modulus size.
"""
import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import logging
import math
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

logger = logging.getLogger("elegance.customer_identity")

ALGORITHM = "RS256"
MAX_TOKEN_CHARS = 4096
MAX_KEYS = 20
MIN_MODULUS_BITS, MAX_MODULUS_BITS = 2048, 8192
LEEWAY_SECONDS = 30
_SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
_B64URL = re.compile(r"[A-Za-z0-9_-]+")
_FORBIDDEN_HEADERS = ("crit", "jku", "jwk", "x5u", "x5c")


class IdentityRejected(Exception):
    """The token is not acceptable. Messages are generic labels: never token or claim content."""


class JwksUnavailable(Exception):
    """Signing keys cannot be obtained right now (a service problem, not a bad token)."""


@dataclass(frozen=True)
class ExternalIdentity:
    issuer: str
    subject: str


def _unb64(segment: object) -> bytes:
    if not isinstance(segment, str) or not _B64URL.fullmatch(segment):
        raise ValueError("not base64url")
    try:
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except (binascii.Error, ValueError):
        raise ValueError("not base64url") from None


def _json_object(raw: bytes) -> dict:
    def refuse(_):
        raise ValueError("non-finite number")

    value = json.loads(raw.decode("utf-8"), parse_constant=refuse)
    if not isinstance(value, dict):
        raise ValueError("not an object")
    return value


def _rs256_valid(n: int, e: int, signing_input: bytes, signature: bytes) -> bool:
    size = (n.bit_length() + 7) // 8
    s = int.from_bytes(signature, "big")
    if len(signature) != size or s >= n:
        return False
    digest_info = _SHA256_DIGEST_INFO + hashlib.sha256(signing_input).digest()
    expected = b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3) + b"\x00" + digest_info
    return hmac.compare_digest(pow(s, e, n).to_bytes(size, "big"), expected)


def _parse_jwks(doc: object) -> dict[str, tuple[int, int]]:
    keys = doc.get("keys") if isinstance(doc, dict) else None
    if not isinstance(keys, list) or len(keys) > MAX_KEYS:
        raise ValueError("unusable JWKS document")
    parsed: dict[str, tuple[int, int]] = {}
    for jwk in keys:
        if not isinstance(jwk, dict) or jwk.get("kty") != "RSA" or jwk.get("use") not in (None, "sig") or jwk.get("alg") not in (None, ALGORITHM):
            continue                                                 # not for us (other algorithms or purposes)
        kid = jwk.get("kid")
        if not isinstance(kid, str) or not 1 <= len(kid) <= 128:
            continue
        try:
            n, e = int.from_bytes(_unb64(jwk.get("n")), "big"), int.from_bytes(_unb64(jwk.get("e")), "big")
        except ValueError:
            continue
        if not MIN_MODULUS_BITS <= n.bit_length() <= MAX_MODULUS_BITS or e < 3 or e % 2 == 0 or e.bit_length() > 32:
            continue
        if kid in parsed:
            raise ValueError("ambiguous JWKS document")
        parsed[kid] = (n, e)
    if not parsed:
        raise ValueError("no usable signing key")
    return parsed


class JwksCache:
    def __init__(self, fetch: Callable[[], Awaitable[object]], *, clock: Callable[[], float] = time.monotonic,
                 ttl: float = 3600, min_refresh_interval: float = 60, max_stale: float = 86400):
        self._fetch, self._clock = fetch, clock
        self._ttl, self._min_refresh, self._max_stale = ttl, min_refresh_interval, max_stale
        self._keys: dict[str, tuple[int, int]] = {}
        self._loaded_at: float | None = None
        self._attempted_at: float | None = None
        self._lock = asyncio.Lock()

    def _wants_refresh(self, kid: str, now: float) -> bool:
        stale = self._loaded_at is None or now - self._loaded_at >= self._ttl
        if not (stale or kid not in self._keys):
            return False
        return self._attempted_at is None or now - self._attempted_at >= self._min_refresh

    async def _refresh(self, now: float) -> None:
        self._attempted_at = now                                     # failures are throttled exactly like successes
        try:
            self._keys, self._loaded_at = _parse_jwks(await self._fetch()), now
        except Exception:
            logger.warning("JWKS refresh failed; keeping cached keys within the stale ceiling")

    async def key_for(self, kid: str) -> tuple[int, int]:
        if self._wants_refresh(kid, self._clock()):
            async with self._lock:                                   # single flight; waiters re-check and find it done
                now = self._clock()
                if self._wants_refresh(kid, now):
                    await self._refresh(now)
        if self._loaded_at is None or self._clock() - self._loaded_at > self._max_stale:
            self._keys, self._loaded_at = {}, None
            raise JwksUnavailable("signing keys unavailable")
        key = self._keys.get(kid)
        if key is None:
            raise IdentityRejected("unknown signing key")
        return key


class HttpJwksFetcher:
    """Fetches the JWKS document: https only, short timeout, no redirects, response size capped."""

    def __init__(self, url: str, *, timeout: float = 3.0, max_bytes: int = 65536, transport: httpx.AsyncBaseTransport | None = None):
        if not url.startswith("https://"):
            raise ValueError("The JWKS URL must be https")
        self._url, self._timeout, self._max_bytes, self._transport = url, timeout, max_bytes, transport

    async def __call__(self) -> object:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False, transport=self._transport) as client:
            async with client.stream("GET", self._url, headers={"Accept": "application/json"}) as response:
                response.raise_for_status()
                body = b""
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > self._max_bytes:
                        raise ValueError("JWKS response too large")
        return json.loads(body)


def _timestamp(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise IdentityRejected("invalid time claim")
    return float(value)


class ExternalIdentityVerifier:
    def __init__(self, *, issuer: str, audience: str, keys: JwksCache, leeway: int = LEEWAY_SECONDS):
        if not issuer or not audience:
            raise ValueError("issuer and audience are required")
        self._issuer, self._audience, self._keys, self._leeway = issuer, audience, keys, leeway

    async def verify(self, token: str, now: datetime) -> ExternalIdentity:
        if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_CHARS:
            raise IdentityRejected("malformed token")
        parts = token.split(".")
        if len(parts) != 3:
            raise IdentityRejected("malformed token")
        try:
            header, claims, signature = _json_object(_unb64(parts[0])), _json_object(_unb64(parts[1])), _unb64(parts[2])
        except ValueError:                                           # includes bad UTF-8 and bad JSON
            raise IdentityRejected("malformed token") from None
        kid = header.get("kid")
        if header.get("alg") != ALGORITHM or any(h in header for h in _FORBIDDEN_HEADERS) \
                or not isinstance(kid, str) or not 1 <= len(kid) <= 128:
            raise IdentityRejected("unacceptable header")
        n, e = await self._keys.key_for(kid)                         # only a structurally valid token may cost a lookup
        if not _rs256_valid(n, e, f"{parts[0]}.{parts[1]}".encode("ascii"), signature):
            raise IdentityRejected("bad signature")
        return self._claims(claims, now.timestamp())

    def _claims(self, claims: dict, now: float) -> ExternalIdentity:
        if claims.get("iss") != self._issuer:
            raise IdentityRejected("wrong issuer")
        aud = claims.get("aud")
        if not (aud == self._audience if isinstance(aud, str) else isinstance(aud, list) and len(aud) <= 10
                and all(isinstance(a, str) for a in aud) and self._audience in aud):
            raise IdentityRejected("wrong audience")
        if "exp" not in claims or _timestamp(claims["exp"]) <= now - self._leeway:
            raise IdentityRejected("expired")
        if "nbf" in claims and _timestamp(claims["nbf"]) > now + self._leeway:
            raise IdentityRejected("not yet valid")
        if "iat" in claims and _timestamp(claims["iat"]) > now + self._leeway:
            raise IdentityRejected("issued in the future")
        sub = claims.get("sub")
        if not isinstance(sub, str) or not 1 <= len(sub) <= 255 or sub != sub.strip() or not sub.isprintable():
            raise IdentityRejected("invalid subject")
        return ExternalIdentity(self._issuer, sub)
