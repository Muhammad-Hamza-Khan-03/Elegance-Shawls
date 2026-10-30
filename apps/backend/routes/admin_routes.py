"""Individual admin accounts: login/logout/password, account management (owners) and audit review (owners).

The browser never talks to these routes: the Next.js server logs in on its behalf, keeps the session token in an
HttpOnly cookie and forwards it as X-Admin-Session. Mutations here are audited by the shared guard
(security.admin_auth); login and denied attempts write their own rows because there is no principal yet.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from database.pg import get_pg_session
from repositories import Conflict, NotFound
from repositories import admin as repo
from repositories.admin import EMAIL_EXISTS, LAST_OWNER
from schemas.admin_schema import (
    AccountCreateRequest, AccountListResponse, AccountResponse, AccountUpdateRequest, AuditListResponse, LoginRequest,
    PasswordChangeRequest, PasswordResetRequest, SessionResponse, WhoAmIResponse,
)
from security.admin_auth import ACCOUNTS_MANAGE, AUDIT_READ, SELF, Principal, require_permission
from security.passwords import hash_password_async, password_problem, verify_password_async

auth_router = APIRouter(prefix="/v1/admin/auth", tags=["Admin accounts"])
accounts_router = APIRouter(prefix="/v1/admin/accounts", tags=["Admin accounts"])
audit_router = APIRouter(prefix="/v1/admin/audit", tags=["Admin accounts"])

_BAD_LOGIN = "Invalid email or password"


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid identifier") from exc


def _check_password(password: str, email: str) -> None:
    if problem := password_problem(password, email):
        raise HTTPException(status_code=422, detail=problem)


def _account_only(principal: Principal) -> uuid.UUID:
    if principal.account_id is None:
        raise HTTPException(status_code=403, detail="The shared admin key has no individual account")
    return principal.account_id


# ---- login / session --------------------------------------------------------------------------
@auth_router.post("/login", response_model=SessionResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_pg_session)):
    """Every failure is the same 401, and unknown emails cost the same scrypt as known ones."""
    async with session.begin():
        account = await repo.get_account_by_email(session, payload.email)
        password_ok = await verify_password_async(payload.password, account.password_hash if account else None)
        if account is None:
            reason = "unknown_account"
        elif not password_ok:
            reason = "bad_password"
        elif account.status != "active":
            reason = "account_disabled"
        elif account.locked_until and account.locked_until > datetime.now(timezone.utc):
            reason = "account_locked"
        else:
            reason = None
        if reason is None:
            token, session_id, expires_at = await repo.create_session(session, account.id, settings.admin_session_ttl_seconds)
            await repo.register_successful_login(session, account.id)
            await repo.add_audit(session, actor_type="admin", actor_id=str(account.id), action="auth.login",
                                 target=f"admin_account:{account.id}", outcome="success", detail={"session_id": str(session_id)})
            await session.refresh(account)
            return SessionResponse(token=token, expires_at=expires_at, account=AccountResponse.model_validate(account))
        if reason == "bad_password" and account.status == "active":
            await repo.register_failed_login(session, account.id, settings.admin_login_max_failures, settings.admin_login_lockout_seconds)
        # The attempted email is deliberately not recorded: a mistyped password in that field would be written to the log.
        await repo.add_audit(session, actor_type="admin", actor_id=str(account.id) if account else None, action="auth.login",
                             target=f"admin_account:{account.id}" if account else None, outcome="denied", detail={"reason": reason})
    raise HTTPException(status_code=401, detail=_BAD_LOGIN)


@auth_router.get("/me", response_model=WhoAmIResponse)
async def me(principal: Principal = Depends(require_permission(SELF)), session: AsyncSession = Depends(get_pg_session)):
    account = None
    if principal.account_id:
        async with session.begin():
            account = await repo.get_account(session, principal.account_id)
    return WhoAmIResponse(account=AccountResponse.model_validate(account) if account else None, role=principal.role, legacy=principal.legacy)


@auth_router.post("/logout")
async def logout(principal: Principal = Depends(require_permission(SELF)), session: AsyncSession = Depends(get_pg_session)):
    if principal.session_id:
        async with session.begin():
            await repo.revoke_session(session, principal.session_id, "logout")
    return {"ok": True}


@auth_router.post("/password", response_model=SessionResponse)
async def change_own_password(
    payload: PasswordChangeRequest,
    request: Request,
    principal: Principal = Depends(require_permission(SELF)),
    session: AsyncSession = Depends(get_pg_session),
):
    """Revokes every session of the account, including this one, and issues a fresh token (rotation)."""
    account_id = _account_only(principal)
    wrong = False
    async with session.begin():
        account = await repo.get_account(session, account_id)
        if await verify_password_async(payload.current_password, account.password_hash):
            _check_password(payload.new_password, account.email)
        else:
            # Counts toward lockout, so a stolen session cannot be used to grind the current password.
            await repo.register_failed_login(session, account_id, settings.admin_login_max_failures, settings.admin_login_lockout_seconds)
            wrong = True
    if wrong:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    new_hash = await hash_password_async(payload.new_password)
    async with session.begin():
        await repo.set_password(session, account_id, new_hash)
        token, _, expires_at = await repo.create_session(session, account_id, settings.admin_session_ttl_seconds)
        account = await repo.get_account(session, account_id)
        await session.refresh(account)
        request.state.audit_detail["sessions_revoked"] = True
        return SessionResponse(token=token, expires_at=expires_at, account=AccountResponse.model_validate(account))


# ---- account management (owner) ---------------------------------------------------------------
@accounts_router.get("", response_model=AccountListResponse, dependencies=[Depends(require_permission(ACCOUNTS_MANAGE))])
async def list_accounts(session: AsyncSession = Depends(get_pg_session)):
    async with session.begin():
        return {"items": await repo.list_accounts(session)}


@accounts_router.post("", response_model=AccountResponse, status_code=201)
async def create_account(
    payload: AccountCreateRequest,
    request: Request,
    principal: Principal = Depends(require_permission(ACCOUNTS_MANAGE)),
    session: AsyncSession = Depends(get_pg_session),
):
    _check_password(payload.password, payload.email)
    password_hash = await hash_password_async(payload.password)
    try:
        async with session.begin():
            account = await repo.create_account(session, email=payload.email, role=payload.role, password_hash=password_hash,
                                                display_name=payload.display_name, created_by=principal.account_id)
            request.state.audit_detail.update(account_id=str(account.id), new_role=account.role)
            return account
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@accounts_router.patch("/{account_id}", response_model=AccountResponse, dependencies=[Depends(require_permission(ACCOUNTS_MANAGE))])
async def update_account(account_id: str, payload: AccountUpdateRequest, request: Request, session: AsyncSession = Depends(get_pg_session)):
    if payload.role is None and payload.status is None:
        raise HTTPException(status_code=422, detail="Nothing to change")
    try:
        async with session.begin():
            account = await repo.update_account(session, _uuid(account_id), role=payload.role, status=payload.status)
            request.state.audit_detail.update(new_role=payload.role, new_status=payload.status)
            return account
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@accounts_router.post("/{account_id}/password", response_model=AccountResponse, dependencies=[Depends(require_permission(ACCOUNTS_MANAGE))])
async def reset_password(account_id: str, payload: PasswordResetRequest, request: Request, session: AsyncSession = Depends(get_pg_session)):
    """Owner reset: all of the account's sessions are revoked and its lockout cleared."""
    target = _uuid(account_id)
    try:
        async with session.begin():
            account = await repo.get_account(session, target)
            if account is None:
                raise NotFound("Account not found")
            _check_password(payload.new_password, account.email)
        new_hash = await hash_password_async(payload.new_password)
        async with session.begin():
            await repo.set_password(session, target, new_hash)
            request.state.audit_detail["sessions_revoked"] = True
            account = await repo.get_account(session, target)
            await session.refresh(account)
            return account
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---- audit review (owner) ---------------------------------------------------------------------
@audit_router.get("", response_model=AuditListResponse, dependencies=[Depends(require_permission(AUDIT_READ))])
async def list_audit(limit: int = Query(default=50, ge=1, le=200), session: AsyncSession = Depends(get_pg_session)):
    async with session.begin():
        return {"items": await repo.list_audit(session, limit)}
