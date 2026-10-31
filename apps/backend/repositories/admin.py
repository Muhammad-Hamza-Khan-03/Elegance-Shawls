"""Admin accounts, server-side sessions and the audit trail. Like the other repositories, nothing here commits."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.relational_model import AdminAccount, AdminSession, AuditLog
from repositories import Conflict, NotFound
from security.passwords import hash_session_token, new_session_token

LAST_OWNER = "last_owner"
EMAIL_EXISTS = "email_exists"


def normalize_email(email: str) -> str:
    return email.strip().lower()


# ---- accounts ---------------------------------------------------------------------------------
async def get_account(session: AsyncSession, account_id: uuid.UUID) -> AdminAccount | None:
    return await session.get(AdminAccount, account_id)


async def get_account_by_email(session: AsyncSession, email: str) -> AdminAccount | None:
    return (await session.execute(select(AdminAccount).where(AdminAccount.email == normalize_email(email)))).scalar_one_or_none()


async def list_accounts(session: AsyncSession) -> list[AdminAccount]:
    return list((await session.execute(select(AdminAccount).order_by(AdminAccount.created_at, AdminAccount.id))).scalars())


async def create_account(session: AsyncSession, *, email: str, role: str, password_hash: str,
                         display_name: str | None = None, created_by: uuid.UUID | None = None) -> AdminAccount:
    row = (await session.execute(
        pg_insert(AdminAccount).values(email=normalize_email(email), role=role, password_hash=password_hash,
                                       display_name=display_name, created_by=created_by)
        .on_conflict_do_nothing(index_elements=["email"]).returning(AdminAccount)
    )).scalar_one_or_none()
    if row is None:
        raise Conflict("An account with this email already exists", EMAIL_EXISTS)
    return row


async def _active_owner_ids_locked(session: AsyncSession) -> set[uuid.UUID]:
    """Serialises concurrent demotions/disablements so the last owner can never be removed."""
    rows = await session.execute(select(AdminAccount.id).where(AdminAccount.role == "owner", AdminAccount.status == "active")
                                 .order_by(AdminAccount.id).with_for_update())
    return set(rows.scalars())


async def update_account(session: AsyncSession, account_id: uuid.UUID, *, role: str | None = None, status: str | None = None) -> AdminAccount:
    owners = await _active_owner_ids_locked(session)    # always first and in id order, so two demotions cannot deadlock
    account = await session.get(AdminAccount, account_id, with_for_update=True)
    if account is None:
        raise NotFound("Account not found")
    new_role, new_status = role or account.role, status or account.status
    loses_owner = account.role == "owner" and account.status == "active" and (new_role != "owner" or new_status != "active")
    if loses_owner and not owners - {account.id}:
        raise Conflict("At least one active owner must remain", LAST_OWNER)
    if new_status == "disabled" and account.status != "disabled":
        account.disabled_at = datetime.now(timezone.utc)
        await revoke_account_sessions(session, account.id, "account_disabled")
    elif new_status == "active":
        account.disabled_at = None
    if new_role != account.role:
        await revoke_account_sessions(session, account.id, "role_changed")   # no session outlives its old privileges
    account.role, account.status = new_role, new_status
    await session.flush()
    await session.refresh(account)
    return account


async def set_password(session: AsyncSession, account_id: uuid.UUID, password_hash: str, *, keep_session: uuid.UUID | None = None) -> None:
    result = await session.execute(update(AdminAccount).where(AdminAccount.id == account_id).values(
        password_hash=password_hash, password_changed_at=func.now(), failed_login_count=0, locked_until=None))
    if result.rowcount == 0:
        raise NotFound("Account not found")
    await revoke_account_sessions(session, account_id, "password_changed", except_session=keep_session)


async def register_failed_login(session: AsyncSession, account_id: uuid.UUID, max_failures: int, lockout_seconds: int) -> None:
    """Atomic: the Nth consecutive failure starts the lockout and resets the counter."""
    count = AdminAccount.failed_login_count + 1
    await session.execute(update(AdminAccount).where(AdminAccount.id == account_id).values(
        failed_login_count=case((count >= max_failures, 0), else_=count),
        locked_until=case((count >= max_failures, func.now() + timedelta(seconds=lockout_seconds)), else_=AdminAccount.locked_until),
    ))


async def register_successful_login(session: AsyncSession, account_id: uuid.UUID) -> None:
    await session.execute(update(AdminAccount).where(AdminAccount.id == account_id).values(
        failed_login_count=0, locked_until=None, last_login_at=func.now()))


# ---- sessions ---------------------------------------------------------------------------------
async def create_session(session: AsyncSession, account_id: uuid.UUID, ttl_seconds: int) -> tuple[str, uuid.UUID, datetime]:
    token, digest = new_session_token()
    row = (await session.execute(
        pg_insert(AdminSession).values(account_id=account_id, token_hash=digest, expires_at=func.now() + timedelta(seconds=ttl_seconds))
        .returning(AdminSession.id, AdminSession.expires_at)
    )).one()
    return token, row.id, row.expires_at


async def authenticate_session(session: AsyncSession, token: str):
    """(session id, account) for a live session of an active account, else None."""
    row = (await session.execute(
        select(AdminSession.id, AdminAccount)
        .join(AdminAccount, AdminAccount.id == AdminSession.account_id)
        .where(AdminSession.token_hash == hash_session_token(token), AdminSession.revoked_at.is_(None),
               AdminSession.expires_at > func.now(), AdminAccount.status == "active")
    )).one_or_none()
    return (row[0], row[1]) if row else None


async def revoke_session(session: AsyncSession, session_id: uuid.UUID, reason: str) -> None:
    await session.execute(update(AdminSession).where(AdminSession.id == session_id, AdminSession.revoked_at.is_(None))
                          .values(revoked_at=func.now(), revoked_reason=reason))


async def revoke_account_sessions(session: AsyncSession, account_id: uuid.UUID, reason: str, *, except_session: uuid.UUID | None = None) -> None:
    stmt = update(AdminSession).where(AdminSession.account_id == account_id, AdminSession.revoked_at.is_(None))
    if except_session is not None:
        stmt = stmt.where(AdminSession.id != except_session)
    await session.execute(stmt.values(revoked_at=func.now(), revoked_reason=reason))


# ---- audit ------------------------------------------------------------------------------------
async def add_audit(session: AsyncSession, *, actor_type: str, actor_id: str | None, action: str, target: str | None,
                    outcome: str, detail: dict | None = None) -> uuid.UUID:
    return (await session.execute(
        pg_insert(AuditLog).values(actor_type=actor_type, actor_id=actor_id, action=action, target=target, outcome=outcome, detail=detail)
        .returning(AuditLog.id)
    )).scalar_one()


async def finalize_audit(session: AsyncSession, audit_id: uuid.UUID, outcome: str, detail: dict | None) -> None:
    await session.execute(update(AuditLog).where(AuditLog.id == audit_id, AuditLog.outcome == "accepted")
                          .values(outcome=outcome, detail=detail))


async def list_audit(session: AsyncSession, limit: int) -> list[AuditLog]:
    return list((await session.execute(select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit))).scalars())
