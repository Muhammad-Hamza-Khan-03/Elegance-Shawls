"""Signed anonymous session tokens: `v1.<random id>.<hmac>`. Carries no personal data."""
import hashlib
import hmac
import secrets

from configuration.config import settings


def _sign(session_id: str) -> str:
    return hmac.new(settings.session_signing_key.encode(), f"v1.{session_id}".encode(), hashlib.sha256).hexdigest()[:32]


def mint_session_token() -> str:
    session_id = secrets.token_hex(16)
    return f"v1.{session_id}.{_sign(session_id)}"


def verify_session_token(token: str | None) -> str | None:
    """Returns the session id for a valid token, else None."""
    if not token or not settings.session_signing_key:
        return None
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1" or len(parts[1]) != 32:
        return None
    return parts[1] if hmac.compare_digest(parts[2], _sign(parts[1])) else None
