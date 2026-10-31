"""Offline fixtures for customer authentication tests: a throwaway stdlib RSA key (never a real credential), an RS256 signer,
and a JWKS document builder. The production verifier needs no such code; it only holds public keys."""
import base64
import hashlib
import json
import random
import time

ISSUER = "https://idp.test.invalid"
AUDIENCE = "elegance-test-audience"
_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")     # DigestInfo for SHA-256
_SMALL = [p for p in range(3, 2000, 2) if all(p % q for q in range(3, int(p ** 0.5) + 1, 2))]


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _prime(bits: int, rng: random.Random) -> int:
    while True:
        c = rng.getrandbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if any(c % p == 0 for p in _SMALL):
            continue
        if _miller_rabin(c, rng):
            return c


def _miller_rabin(n: int, rng: random.Random, rounds: int = 12) -> bool:
    d, r = n - 1, 0
    while d % 2 == 0:
        d, r = d // 2, r + 1
    for _ in range(rounds):
        x = pow(rng.randrange(2, n - 2), d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


class TestKey:
    __test__ = False

    def __init__(self, seed: int, bits: int = 2048, kid: str = "k1"):
        rng = random.Random(seed)                      # deterministic throwaway key
        self.e, self.kid = 65537, kid
        while True:
            p, q = _prime(bits // 2, rng), _prime(bits // 2, rng)
            if p != q and (p - 1) % self.e and (q - 1) % self.e and (p * q).bit_length() == bits:
                break
        self.n, self.d = p * q, pow(self.e, -1, (p - 1) * (q - 1))

    def jwk(self, **over) -> dict:
        size = (self.n.bit_length() + 7) // 8
        return {"kty": "RSA", "kid": self.kid, "use": "sig", "alg": "RS256", "n": b64u(self.n.to_bytes(size, "big")),
                "e": b64u(self.e.to_bytes(3, "big")), **over}

    def sign(self, signing_input: bytes) -> bytes:
        size = (self.n.bit_length() + 7) // 8
        t = _PREFIX + hashlib.sha256(signing_input).digest()
        em = b"\x00\x01" + b"\xff" * (size - len(t) - 3) + b"\x00" + t
        return pow(int.from_bytes(em, "big"), self.d, self.n).to_bytes(size, "big")


_KEYS: dict[int, TestKey] = {}


def key(seed: int = 1, kid: str = "k1") -> TestKey:
    k = _KEYS[seed] = _KEYS.get(seed) or TestKey(seed)
    k.kid = kid
    return k


def jwks(*keys: TestKey) -> dict:
    return {"keys": [k.jwk() for k in keys]}


def claims(**over) -> dict:
    now = int(time.time())
    base = {"iss": ISSUER, "aud": AUDIENCE, "sub": "subject-123", "iat": now, "nbf": now - 5, "exp": now + 300}
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def token(signer: TestKey | None = None, payload: dict | None = None, header: dict | None = None, *, sign_with: TestKey | None = None) -> str:
    signer = signer or key()
    h = {"alg": "RS256", "typ": "JWT", "kid": signer.kid, **(header or {})}
    h = {k: v for k, v in h.items() if v is not None}
    body = b64u(json.dumps(h).encode()) + "." + b64u(json.dumps(claims() if payload is None else payload).encode())
    return body + "." + b64u((sign_with or signer).sign(body.encode()))
