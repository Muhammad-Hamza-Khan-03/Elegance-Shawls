"""M4 customer authentication: external identity verification and the bounded JWKS cache, fully offline (no network, no real keys)."""
import asyncio
import json
import time
from datetime import datetime, timezone

import httpx
import pytest

from security.customer_identity import (
    ExternalIdentityVerifier, HttpJwksFetcher, IdentityRejected, JwksCache, JwksUnavailable,
)
from tests.customer_auth_support import AUDIENCE, ISSUER, b64u, claims, jwks, key, token

for _seed in (1, 2, 3):
    key(_seed)                       # generate the throwaway keys at import, not inside a timed case


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Fetcher:
    def __init__(self, *docs):
        self.docs, self.calls = list(docs), 0

    async def __call__(self):
        self.calls += 1
        doc = self.docs[min(self.calls, len(self.docs)) - 1]
        if isinstance(doc, Exception):
            raise doc
        return doc


def cache(fetch, clock=None, **kw):
    return JwksCache(fetch, clock=clock or Clock(), **kw)


def verifier(fetch=None, **kw):
    return ExternalIdentityVerifier(issuer=ISSUER, audience=AUDIENCE, keys=cache(fetch or Fetcher(jwks(key()))), **kw)


def verify(v, tok, now=None):
    return asyncio.run(v.verify(tok, now or datetime.now(timezone.utc)))


def rejected(tok, **kw):
    with pytest.raises(IdentityRejected):
        verify(verifier(**kw), tok)


# ---- accepted ----------------------------------------------------------------------------------
def test_valid_token_yields_issuer_and_subject_only():
    identity = verify(verifier(), token())
    assert (identity.issuer, identity.subject) == (ISSUER, "subject-123")


def test_audience_list_containing_ours_is_accepted():
    assert verify(verifier(), token(payload=claims(aud=["other", AUDIENCE]))).subject == "subject-123"


# ---- strict header ------------------------------------------------------------------------------
@pytest.mark.parametrize("header", [
    {"alg": "none"}, {"alg": "HS256"}, {"alg": "RS384"}, {"alg": "rs256"}, {"alg": None}, {"alg": ["RS256"]},
    {"kid": None}, {"kid": ""}, {"kid": 7}, {"kid": "x" * 200},
    {"crit": ["exp"]}, {"jku": "https://evil.invalid/jwks"}, {"jwk": {"kty": "RSA"}}, {"x5u": "https://evil.invalid/c"},
])
def test_bad_header_is_rejected(header):
    rejected(token(header=header))


def test_unsigned_and_hmac_confusion_tokens_are_rejected():
    head = b64u(json.dumps({"alg": "none", "kid": "k1"}).encode())
    body = b64u(json.dumps(claims()).encode())
    rejected(f"{head}.{body}.")
    rejected(f"{head}.{body}")


@pytest.mark.parametrize("tok", ["", "a.b", "a.b.c.d", "a..c", "....", "x" * 5000, "a b.c.d", "é.é.é", "a.b.c=="])
def test_malformed_tokens_are_rejected(tok):
    rejected(tok)


def test_non_object_header_or_payload_is_rejected():
    for h, p in ((b"[]", b"{}"), (b"{}", b"[]"), (b"null", b"{}"), (b"{", b"{}")):
        rejected(f"{b64u(h)}.{b64u(p)}.{b64u(b'x' * 256)}")


# ---- signature ----------------------------------------------------------------------------------
def test_signature_by_another_key_is_rejected():
    rejected(token(key(), sign_with=key(2, "other")))


def test_tampered_payload_is_rejected():
    head, _, sig = token().split(".")
    rejected(f"{head}.{b64u(json.dumps(claims(sub='someone-else')).encode())}.{sig}")


def test_truncated_or_padded_signature_is_rejected():
    head, body, sig = token().split(".")
    rejected(f"{head}.{body}.{sig[:-4]}")
    rejected(f"{head}.{body}.{sig}AAAA")


def test_unknown_kid_is_rejected():
    rejected(token(key(1, "unlisted"), ), fetch=Fetcher(jwks(key(2, "listed"))))


# ---- strict claims ------------------------------------------------------------------------------
# Time-relative values are callables of "now", resolved when the case runs (the suite is slow; a fixed import-time clock would drift).
def resolved(over):
    now = int(time.time())
    return {k: v(now) if callable(v) else v for k, v in over.items()}


@pytest.mark.parametrize("over", [
    {"iss": "https://evil.invalid"}, {"iss": ISSUER + "/"}, {"iss": None}, {"iss": 5}, {"iss": [ISSUER]},
    {"aud": "someone-else"}, {"aud": None}, {"aud": []}, {"aud": ["a", "b"]}, {"aud": AUDIENCE + "x"}, {"aud": 7}, {"aud": [AUDIENCE, 7]},
    {"exp": None}, {"exp": lambda n: n - 3600}, {"exp": "9999999999"}, {"exp": True}, {"exp": float("nan")}, {"exp": lambda n: n - 40},
    {"nbf": lambda n: n + 3600}, {"nbf": lambda n: n + 40}, {"nbf": "0"}, {"nbf": True},
    {"iat": lambda n: n + 3600},
    {"sub": None}, {"sub": ""}, {"sub": "   "}, {"sub": 12}, {"sub": "x" * 256}, {"sub": "bad\x00sub"}, {"sub": " padded "}, {"sub": "new\nline"},
])
def test_bad_claims_are_rejected(over):
    rejected(token(payload=claims(**resolved(over))))


def test_small_clock_skew_is_tolerated_but_bounded():
    assert verify(verifier(), token(payload=claims(**resolved({"exp": lambda n: n - 5, "nbf": lambda n: n + 5})))).subject == "subject-123"


def test_expiry_is_judged_against_the_supplied_clock():
    tok = token(payload=claims(exp=int(time.time()) + 60))
    assert verify(verifier(), tok).subject
    with pytest.raises(IdentityRejected):
        verify(verifier(), tok, datetime.fromtimestamp(time.time() + 3600, timezone.utc))


def test_rejection_never_echoes_token_or_claims():
    tok = token(payload=claims(sub="secret-subject"))
    with pytest.raises(IdentityRejected) as exc:
        verify(verifier(), tok.rsplit(".", 1)[0] + "." + b64u(b"x" * 256))
    assert "secret-subject" not in str(exc.value) and tok not in str(exc.value)


# ---- JWKS cache: bounded refresh ----------------------------------------------------------------
def test_keys_are_cached_between_verifications():
    f = Fetcher(jwks(key()))
    v = ExternalIdentityVerifier(issuer=ISSUER, audience=AUDIENCE, keys=cache(f))
    for _ in range(5):
        verify(v, token())
    assert f.calls == 1


def test_unknown_kids_cannot_force_a_refresh_per_request():
    clock, f = Clock(), Fetcher(jwks(key()))
    c = cache(f, clock, min_refresh_interval=60)
    run = lambda kid: asyncio.run(c.key_for(kid))
    run("k1")
    for i in range(20):
        with pytest.raises(IdentityRejected):
            run(f"forged-{i}")
    assert f.calls == 1
    clock.t += 61
    with pytest.raises(IdentityRejected):
        run("forged-again")
    assert f.calls == 2


def test_key_rotation_is_picked_up_after_the_minimum_interval():
    clock, f = Clock(), Fetcher(jwks(key(1, "old")), jwks(key(1, "old"), key(2, "new")))
    c = cache(f, clock, min_refresh_interval=60)
    asyncio.run(c.key_for("old"))
    with pytest.raises(IdentityRejected):
        asyncio.run(c.key_for("new"))
    clock.t += 61
    assert asyncio.run(c.key_for("new"))


def test_expired_cache_refreshes_once_for_concurrent_callers():
    clock, f = Clock(), Fetcher(jwks(key()))
    c = cache(f, clock, ttl=100)

    async def go():
        await c.key_for("k1")
        clock.t += 101
        await asyncio.gather(*(c.key_for("k1") for _ in range(10)))

    asyncio.run(go())
    assert f.calls == 2


def test_failed_refresh_serves_cached_keys_until_the_stale_ceiling_then_fails_closed():
    clock = Clock()
    f = Fetcher(jwks(key()), RuntimeError("down"))
    c = cache(f, clock, ttl=100, min_refresh_interval=10, max_stale=500)
    asyncio.run(c.key_for("k1"))
    clock.t += 200
    assert asyncio.run(c.key_for("k1"))                     # stale but inside the ceiling
    clock.t += 400
    with pytest.raises(JwksUnavailable):
        asyncio.run(c.key_for("k1"))


def test_failures_are_throttled_too_and_first_load_failure_is_unavailable():
    clock, f = Clock(), Fetcher(RuntimeError("down"))
    c = cache(f, clock, min_refresh_interval=60)
    for _ in range(10):
        with pytest.raises(JwksUnavailable):
            asyncio.run(c.key_for("k1"))
    assert f.calls == 1


def test_jwks_documents_are_bounded_and_filtered():
    good = key()
    weak = key(3, "weak")
    weak.n = (1 << 1023) + 1                                  # 1024-bit modulus
    many = {"keys": [{**good.jwk(), "kid": f"k{i}"} for i in range(25)]}
    cases = {
        "too many keys": many,
        "not an object": ["keys"],
        "no keys": {"keys": []},
        "non-rsa": {"keys": [{"kty": "oct", "kid": "k1", "k": "AAAA"}]},
        "wrong alg": {"keys": [good.jwk(alg="HS256")]},
        "enc use": {"keys": [good.jwk(use="enc")]},
        "weak modulus": {"keys": [weak.jwk(kid="k1")]},
        "bad exponent": {"keys": [good.jwk(e="AQ")]},       # e = 1
        "private fields only ignored? no: junk n": {"keys": [good.jwk(n="!!")]},
    }
    for name, doc in cases.items():
        c = cache(Fetcher(doc))
        with pytest.raises((IdentityRejected, JwksUnavailable)):
            asyncio.run(c.key_for("k1"))
    assert asyncio.run(cache(Fetcher({"keys": [good.jwk(use=None, alg=None)]})).key_for("k1"))


# ---- HTTP fetcher (offline MockTransport) --------------------------------------------------------
def fetcher(handler, **kw):
    return HttpJwksFetcher("https://idp.test.invalid/jwks", transport=httpx.MockTransport(handler), **kw)


def test_http_fetcher_returns_json_and_never_follows_redirects():
    assert asyncio.run(fetcher(lambda r: httpx.Response(200, json=jwks(key())))())["keys"]
    redirect = fetcher(lambda r: httpx.Response(302, headers={"location": "https://evil.invalid/"}))
    with pytest.raises(Exception):
        asyncio.run(redirect())


@pytest.mark.parametrize("response", [
    httpx.Response(500), httpx.Response(200, content=b"not json"), httpx.Response(200, content=b"x" * 100_000),
])
def test_http_fetcher_rejects_errors_garbage_and_oversize(response):
    with pytest.raises(Exception):
        asyncio.run(fetcher(lambda r: response, max_bytes=1000)())


def test_http_fetcher_requires_https():
    with pytest.raises(ValueError):
        HttpJwksFetcher("http://idp.test.invalid/jwks")
