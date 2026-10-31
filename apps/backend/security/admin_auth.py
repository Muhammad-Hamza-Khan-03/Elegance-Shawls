"""Admin authentication, role authorization and mutation auditing, enforced by one FastAPI dependency.

Credentials, in order of preference:
* `X-Admin-Session`: opaque server-side session token of an individual account (sent by the Next.js proxy only);
* `X-Admin-Key`: the legacy shared key, honoured only until ADMIN_LEGACY_KEY_EXPIRES_AT (see config), as a
  migration path. It is never the default and every use is audited as actor `legacy-shared-key`.

Authorization is default-deny by method: a safe method needs `catalogue:read`, anything else `catalogue:write`,
unless the route asks for a specific permission. Every authorised mutation is written to audit_log BEFORE the
handler runs (a failing audit write refuses the request) and finalised to success/failure afterwards.
"""
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from database.pg import get_pg_session
from repositories import admin as repo

logger = logging.getLogger("elegance.admin_auth")

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SELF, CATALOGUE_READ, CATALOGUE_WRITE = "self", "catalogue:read", "catalogue:write"
ACCOUNTS_MANAGE, AUDIT_READ, PLATFORM_OPERATE = "accounts:manage", "audit:read", "platform:operate"
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset({SELF, CATALOGUE_READ}),
    "editor": frozenset({SELF, CATALOGUE_READ, CATALOGUE_WRITE}),
    "owner": frozenset({SELF, CATALOGUE_READ, CATALOGUE_WRITE, ACCOUNTS_MANAGE, AUDIT_READ, PLATFORM_OPERATE}),
}
# The shared key could do everything except manage identities; keep exactly that, no more.
LEGACY_PERMISSIONS = ROLE_PERMISSIONS["editor"] | {PLATFORM_OPERATE}
LEGACY_ACTOR_ID = "legacy-shared-key"


@dataclass(frozen=True)
class Principal:
    role: str
    account_id: uuid.UUID | None = None
    email: str | None = None
    session_id: uuid.UUID | None = None
    legacy: bool = False

    @property
    def permissions(self) -> frozenset[str]:
        return LEGACY_PERMISSIONS if self.legacy else ROLE_PERMISSIONS.get(self.role, frozenset())

    @property
    def actor_id(self) -> str:
        return LEGACY_ACTOR_ID if self.legacy else str(self.account_id)


def legacy_key_expiry() -> datetime | None:
    try:
        expiry = datetime.fromisoformat(settings.admin_legacy_key_expires_at.strip())
    except ValueError:
        return None
    return expiry if expiry.tzinfo else None        # a naive date would be ambiguous: treat as not enabled


def legacy_key_enabled(now: datetime | None = None) -> bool:
    expiry = legacy_key_expiry()
    return bool(settings.admin_api_key and expiry and (now or datetime.now(timezone.utc)) < expiry)


def legacy_key_matches(provided: str) -> bool:
    return legacy_key_enabled() and secrets.compare_digest(provided.encode(), settings.admin_api_key.encode())


async def _authenticate(session: AsyncSession, token: str | None, key: str | None) -> tuple[Principal | None, bool]:
    """(principal or None, whether any credential was presented)."""
    if token:
        found = await repo.authenticate_session(session, token.strip())
        if found is None:
            return None, True
        session_id, account = found
        return Principal(account.role, account.id, account.email, session_id), True
    if key:
        return (Principal("editor", legacy=True) if legacy_key_matches(key) else None), True
    return None, False


def _action(request: Request) -> str:
    """'POST /products/admin/{product_id}/status': the full path template, so actions group by endpoint, not by id."""
    path = request.url.path
    for name, value in request.path_params.items():
        path = path.replace(f"/{value}", f"/{{{name}}}", 1)
    return f"{request.method} {path}"


def _unauthorized() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid administrative credentials", headers={"WWW-Authenticate": "Session"})


async def _deny(session: AsyncSession, principal: Principal | None, action: str, target: str, status_code: int, reason: str, **extra) -> None:
    await repo.add_audit(session, actor_type="admin", actor_id=principal.actor_id if principal else None, action=action,
                         target=target, outcome="denied", detail={"status": status_code, "reason": reason, **extra})
    await session.commit()


@lru_cache(maxsize=None)
def require_permission(permission: str | None = None):
    """Dependency factory. `permission=None` derives read/write from the HTTP method. Cached so a router-level and a
    handler-level use of the same permission resolve (and audit) once per request."""

    async def guard(
        request: Request,
        session: AsyncSession = Depends(get_pg_session),
        x_admin_session: str | None = Header(default=None, alias="X-Admin-Session"),
        x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    ):
        mutating = request.method not in SAFE_METHODS
        action = _action(request)
        target = request.url.path
        principal, presented = await _authenticate(session, x_admin_session, x_admin_key)
        if principal is None:
            if presented or mutating:      # unauthenticated reads with no credential are noise, not events
                await _deny(session, None, action, target, 401, "invalid_credentials" if presented else "missing_credentials")
            raise _unauthorized()
        needed = permission or (CATALOGUE_WRITE if mutating else CATALOGUE_READ)
        if needed not in principal.permissions:
            await _deny(session, principal, action, target, 403, "insufficient_role", role=principal.role, required=needed)
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role does not permit this action")

        request.state.admin = principal
        request.state.audit_detail = {}
        if not mutating:
            await session.commit()         # end the authentication read so handlers can open their own transaction
            yield principal
            return
        try:
            audit_id = await repo.add_audit(session, actor_type="admin", actor_id=principal.actor_id, action=action,
                                            target=target, outcome="accepted", detail={"role": principal.role})
            await session.commit()
        except Exception as exc:           # fail closed: no mutation without a durable audit record
            logger.error("audit write failed; refusing %s", action, exc_info=exc)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Audit log is unavailable") from exc

        outcome, http_status = "success", None
        try:
            yield principal
        except HTTPException as exc:
            outcome, http_status = "failure", exc.status_code
            raise
        except RequestValidationError:
            outcome, http_status = "failure", 422
            raise
        except BaseException:
            outcome, http_status = "failure", 500
            raise
        finally:
            try:
                if outcome == "failure":
                    await session.rollback()
                detail = {"role": principal.role, **request.state.audit_detail}
                if http_status:
                    detail["status"] = http_status
                await repo.finalize_audit(session, audit_id, outcome, detail)
                await session.commit()
            except Exception as exc:       # the 'accepted' row remains and says the outcome was not recorded
                logger.error("audit finalisation failed for %s", action, exc_info=exc)

    guard.admin_permission = permission or "method"
    return guard


require_admin = require_permission()
