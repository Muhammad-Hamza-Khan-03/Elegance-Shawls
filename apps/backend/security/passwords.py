"""Password and session-token primitives (stdlib only: scrypt, sha256, secrets)."""
import asyncio
import base64
import hashlib
import hmac
import secrets

_N, _R, _P, _KEYLEN = 2**15, 8, 1, 32      # ~32 MiB, tens of ms per hash
_MAXMEM = 64 * 1024 * 1024
MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH = 12, 256
SESSION_TOKEN_PREFIX = "es1."


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, keylen: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=keylen, maxmem=_MAXMEM)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(_scrypt(password, salt, _N, _R, _P, _KEYLEN))}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time compare; a malformed stored hash is simply a failure."""
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        expected_raw = base64.b64decode(expected)
        derived = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p), len(expected_raw))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, expected_raw)


# Verified against when the account does not exist, so unknown and known emails cost the same.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, stored: str | None) -> bool:
    ok = await asyncio.to_thread(verify_password, password, stored or _DUMMY_HASH)
    return ok and stored is not None


def password_problem(password: str, email: str) -> str | None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        return f"Password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters"
    if password.strip().lower() in (email.lower(), email.lower().split("@")[0]):
        return "Password must not be the account email"
    return None


def new_session_token() -> tuple[str, str]:
    """(bearer token for the cookie, sha256 hex to store). The database never holds the token."""
    token = SESSION_TOKEN_PREFIX + secrets.token_urlsafe(32)
    return token, hash_session_token(token)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
