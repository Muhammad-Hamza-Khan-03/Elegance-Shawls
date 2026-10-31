"""/v1/customer/auth: exchange an external identity token for a local opaque session, and end sessions (M4).

The customer is always derived server-side: from the verified token's (issuer, subject) on exchange, from the stored session on
logout. No request field names a customer. Disabled (404) unless customer authentication is fully configured. One transaction per
request, committed here. Rate-limited in its own bucket by security/rate_limit.py.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from database.pg import get_pg_session
from memory.principal import CustomerPrincipal, current_principal
from repositories import customer_auth as repo
from schemas.customer_auth_schema import ExchangeRequest, SessionOut
from security.customer_identity import ExternalIdentityVerifier, IdentityRejected, JwksUnavailable
from security.customer_session import get_identity_verifier

router = APIRouter(prefix="/v1/customer/auth", tags=["Customer auth"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enabled_verifier(verifier: ExternalIdentityVerifier | None = Depends(get_identity_verifier)) -> ExternalIdentityVerifier:
    if verifier is None:                # resolved before the database session, so a disabled deployment never touches it
        raise HTTPException(404, "Not found")
    return verifier


@router.post("/exchange", response_model=SessionOut)
async def exchange(body: ExchangeRequest, response: Response, verifier: ExternalIdentityVerifier = Depends(enabled_verifier),
                   session: AsyncSession = Depends(get_pg_session)):
    now = _now()
    try:
        identity = await verifier.verify(body.id_token, now)
    except IdentityRejected:
        raise HTTPException(401, "Invalid identity token", headers={"WWW-Authenticate": "Session"}) from None
    except JwksUnavailable:
        raise HTTPException(503, "Sign-in is temporarily unavailable") from None
    try:
        customer_id = await repo.customer_for_identity(session, settings.customer_auth_provider, identity.subject)
        token, _, expires_at = await repo.create_session(session, customer_id, now, settings.customer_session_ttl_seconds,
                                                         settings.customer_session_max_active)
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    response.headers["Cache-Control"] = "no-store"
    return SessionOut(session_token=token, expires_at=expires_at)


async def _revoke(session: AsyncSession, work):
    try:
        result = await work
        await session.commit()
        return result
    except BaseException:
        await session.rollback()
        raise


@router.post("/logout", status_code=204)
async def logout(principal: CustomerPrincipal = Depends(current_principal), session: AsyncSession = Depends(get_pg_session)):
    await _revoke(session, repo.revoke_session(session, principal.customer_id, uuid.UUID(principal.session_id), "logout", _now()))
    return Response(status_code=204)


@router.post("/logout-all")
async def logout_all(principal: CustomerPrincipal = Depends(current_principal), session: AsyncSession = Depends(get_pg_session)):
    return {"revoked": await _revoke(session, repo.revoke_all(session, principal.customer_id, "logout_all", _now()))}
