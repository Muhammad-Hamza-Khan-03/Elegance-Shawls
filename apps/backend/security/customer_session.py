"""Customer authentication wiring (M4): configuration gate, the external-identity verifier and the server-side session verifier.

Disabled by default and fail-closed: unless CUSTOMER_AUTH_ENABLED and every required setting is valid, there is no identity
verifier and no session verifier, so exchange is 404 and every customer route is 401. Separate from admin authentication
(security/admin_auth.py): different header, table, token prefix and rate-limit bucket.
"""
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache

from configuration.config import settings
from database.pg import open_session
from memory.principal import CustomerPrincipal
from models.relational_model import IDENTITY_PROVIDERS
from repositories import customer_auth as repo
from security.customer_identity import ExternalIdentityVerifier, HttpJwksFetcher, JwksCache
from security.passwords import hash_session_token

logger = logging.getLogger("elegance.customer_auth")


def customer_auth_ready() -> bool:
    return bool(
        settings.customer_auth_enabled
        and settings.customer_auth_provider in set(IDENTITY_PROVIDERS) - {"anon"}
        and settings.customer_auth_issuer and settings.customer_auth_audience
        and settings.customer_auth_jwks_url.startswith("https://")
        and settings.customer_session_ttl_seconds > 0 and settings.customer_session_max_active > 0
        and settings.customer_auth_jwks_ttl_seconds > 0 and settings.customer_auth_jwks_min_refresh_seconds > 0
    )


@lru_cache(maxsize=4)
def _identity_verifier(issuer: str, audience: str, jwks_url: str, ttl: int, min_refresh: int) -> ExternalIdentityVerifier:
    keys = JwksCache(HttpJwksFetcher(jwks_url), ttl=ttl, min_refresh_interval=min_refresh)
    return ExternalIdentityVerifier(issuer=issuer, audience=audience, keys=keys)


def get_identity_verifier() -> ExternalIdentityVerifier | None:
    if not customer_auth_ready():
        return None
    return _identity_verifier(settings.customer_auth_issuer, settings.customer_auth_audience, settings.customer_auth_jwks_url,
                              settings.customer_auth_jwks_ttl_seconds, settings.customer_auth_jwks_min_refresh_seconds)


get_identity_verifier.cache_clear = _identity_verifier.cache_clear     # config changes (tests) rebuild the cached verifier


class DbSessionVerifier:
    """Resolves an opaque session token to its customer from the server's own table. The token is only a lookup key."""

    def __init__(self, sessions: Callable = open_session):
        self._sessions = sessions

    async def verify(self, token: str, now: datetime) -> CustomerPrincipal | None:
        opened = self._sessions()
        if opened is None:
            return None
        async with opened as session:
            digest = hash_session_token(token)
            found = await repo.live_session(session, digest, now)
        if found is None:
            return None
        session_id, customer_id, expires_at = found
        return CustomerPrincipal(customer_id=customer_id, session_id=str(session_id), token_sha256=digest, expires_at=expires_at)


def build_session_verifier() -> DbSessionVerifier | None:
    return DbSessionVerifier() if customer_auth_ready() else None
