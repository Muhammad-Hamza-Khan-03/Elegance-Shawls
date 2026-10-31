"""Customer identities and server-side sessions. Like the other repositories, nothing here commits.

Only the SHA-256 of a session token is stored. Every read and write of a session is scoped by customer where the caller is a
customer, so one customer's token can never touch another's rows.
"""
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.relational_model import Customer, CustomerIdentity, CustomerSession
from security.passwords import hash_session_token

TOKEN_PREFIX = "cs1."


async def customer_for_identity(session: AsyncSession, provider: str, subject: str) -> uuid.UUID:
    """The customer owning (provider, subject), created on first sight. Safe under concurrent first logins."""
    found = (await session.execute(select(CustomerIdentity.customer_id).where(
        CustomerIdentity.provider == provider, CustomerIdentity.subject == subject))).scalar_one_or_none()
    if found is None:
        fresh = (await session.execute(pg_insert(Customer).values(status="registered").returning(Customer.id))).scalar_one()
        linked = (await session.execute(
            pg_insert(CustomerIdentity).values(customer_id=fresh, provider=provider, subject=subject)
            .on_conflict_do_nothing(index_elements=["provider", "subject"]).returning(CustomerIdentity.customer_id))).scalar_one_or_none()
        if linked is not None:
            return fresh
        await session.execute(delete(Customer).where(Customer.id == fresh))           # lost the race: use the winner's customer
        found = (await session.execute(select(CustomerIdentity.customer_id).where(
            CustomerIdentity.provider == provider, CustomerIdentity.subject == subject))).scalar_one()
    await session.execute(update(Customer).where(Customer.id == found, Customer.status != "registered").values(status="registered"))
    return found


async def create_session(session: AsyncSession, customer_id: uuid.UUID, now: datetime, ttl_seconds: int, max_active: int) -> tuple[str, uuid.UUID, datetime]:
    """(bearer token, session id, expiry). Keeps at most `max_active` live sessions: the oldest are revoked."""
    await session.execute(select(Customer.id).where(Customer.id == customer_id).with_for_update())   # serialise per customer
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    expires = now + timedelta(seconds=ttl_seconds)
    sid = (await session.execute(pg_insert(CustomerSession).values(
        customer_id=customer_id, token_hash=hash_session_token(token), created_at=now, expires_at=expires)
        .returning(CustomerSession.id))).scalar_one()
    newest = select(CustomerSession.id).where(
        CustomerSession.customer_id == customer_id, CustomerSession.revoked_at.is_(None), CustomerSession.expires_at > now
    ).order_by(CustomerSession.created_at.desc(), CustomerSession.id.desc()).limit(max_active)
    await session.execute(update(CustomerSession).where(
        CustomerSession.customer_id == customer_id, CustomerSession.revoked_at.is_(None), CustomerSession.id.not_in(newest))
        .values(revoked_at=now, revoked_reason="session_limit"))
    return token, sid, expires


async def live_session(session: AsyncSession, token_hash: str, now: datetime):
    """(session id, customer id, expires_at) for a live session of a registered customer, else None."""
    row = (await session.execute(
        select(CustomerSession.id, CustomerSession.customer_id, CustomerSession.expires_at)
        .join(Customer, Customer.id == CustomerSession.customer_id)
        .where(CustomerSession.token_hash == token_hash, CustomerSession.revoked_at.is_(None),
               CustomerSession.expires_at > now, Customer.status == "registered")
    )).one_or_none()
    return tuple(row) if row else None


async def revoke_session(session: AsyncSession, customer_id: uuid.UUID, session_id: uuid.UUID, reason: str, now: datetime) -> bool:
    result = await session.execute(update(CustomerSession).where(
        CustomerSession.id == session_id, CustomerSession.customer_id == customer_id, CustomerSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=reason))
    return result.rowcount > 0


async def revoke_all(session: AsyncSession, customer_id: uuid.UUID, reason: str, now: datetime) -> int:
    result = await session.execute(update(CustomerSession).where(
        CustomerSession.customer_id == customer_id, CustomerSession.revoked_at.is_(None), CustomerSession.expires_at > now)
        .values(revoked_at=now, revoked_reason=reason))
    return result.rowcount
