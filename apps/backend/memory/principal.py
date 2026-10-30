"""Customer principal/session seam for /v1/me/memory (M4-S2). No customer authentication exists in this repository, so the default
verifier is absent and every request is refused with 401. A future slice installs a real `CustomerSessionVerifier` through
`get_session_verifier` (dependency override or replacement); nothing here issues, stores or parses credentials.

Integration contract for a verifier: given the opaque token presented in the `X-Customer-Session` header, return a `CustomerPrincipal`
only if the server itself holds a live session for that exact token (expiry, revocation and customer status checked server-side),
otherwise None. `token_sha256` must be the SHA-256 hex of the presented token (session binding). Identity is never read from the
request: the token is only a lookup key, and no id, header, query, cookie or body field is accepted as a customer identifier.
"""
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from fastapi import Depends, HTTPException, Request

SESSION_HEADER = "X-Customer-Session"
_MAX_TOKEN = 512


@dataclass(frozen=True)
class CustomerPrincipal:
    customer_id: uuid.UUID
    session_id: str
    token_sha256: str
    expires_at: datetime


class CustomerSessionVerifier(Protocol):
    async def verify(self, token: str, now: datetime) -> CustomerPrincipal | None: ...


def get_session_verifier() -> CustomerSessionVerifier | None:
    """shortcut: no customer session store exists, so no verifier; replace when customer authentication is built."""
    return None


def _deny() -> HTTPException:
    # One response for every failure so a caller cannot tell absent from invalid, expired or mismatched.
    return HTTPException(401, "Customer authentication is required", headers={"WWW-Authenticate": "Session"})


def _valid(p: object, token: str, now: datetime) -> bool:
    return (
        isinstance(p, CustomerPrincipal)
        and isinstance(p.customer_id, uuid.UUID)
        and isinstance(p.session_id, str) and bool(p.session_id)
        and p.token_sha256 == hashlib.sha256(token.encode()).hexdigest()
        and isinstance(p.expires_at, datetime) and p.expires_at.tzinfo is not None and p.expires_at > now
    )


async def resolve_principal(token: str | None, verifier: CustomerSessionVerifier | None, now: datetime) -> CustomerPrincipal:
    if verifier is None or not token or len(token) > _MAX_TOKEN:
        raise _deny()
    try:
        principal = await verifier.verify(token, now)
    except Exception:  # a broken verifier must fail closed, never open
        raise _deny() from None
    if not _valid(principal, token, now):
        raise _deny()
    return principal


async def current_principal(request: Request, verifier: CustomerSessionVerifier | None = Depends(get_session_verifier)) -> CustomerPrincipal:
    return await resolve_principal(request.headers.get(SESSION_HEADER), verifier, datetime.now(timezone.utc))
