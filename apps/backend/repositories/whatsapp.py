"""WhatsApp contacts, messages and enquiry linkage. Takes an AsyncSession and never commits."""
import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.relational_model import Enquiry, Product, Variant, WhatsAppContact, WhatsAppMessage
from repositories import RepositoryError
from whatsapp.matching import OPEN_STATUSES


async def upsert_contact(session: AsyncSession, *, chat: str, lid: str | None, phone: str | None,
                         name: str | None, seen_at: datetime) -> WhatsAppContact:
    stmt = pg_insert(WhatsAppContact).values(chat_jid=chat, lid=lid, phone_e164=phone, display_name=name, first_seen_at=seen_at, last_seen_at=seen_at)
    stmt = stmt.on_conflict_do_update(index_elements=["chat_jid"], set_={
        "lid": stmt.excluded.lid if lid else WhatsAppContact.lid,
        "display_name": stmt.excluded.display_name if name else WhatsAppContact.display_name,
        "last_seen_at": seen_at,
    }).returning(WhatsAppContact)
    return (await session.execute(stmt, execution_options={"populate_existing": True})).scalar_one()


async def message_exists(session: AsyncSession, wa_message_id: str) -> bool:
    return (await session.execute(select(exists().where(WhatsAppMessage.wa_message_id == wa_message_id)))).scalar_one()


async def insert_message(session: AsyncSession, **values) -> bool:
    """False when this wa_message_id is already stored (redelivery)."""
    stmt = pg_insert(WhatsAppMessage).values(**values).on_conflict_do_nothing(index_elements=["wa_message_id"]).returning(WhatsAppMessage.id)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def enquiry_by_reference(session: AsyncSession, reference: str) -> Enquiry | None:
    return (await session.execute(select(Enquiry).where(Enquiry.reference == reference.upper()))).scalar_one_or_none()


async def open_enquiry_for_contact(session: AsyncSession, contact_id: uuid.UUID) -> Enquiry | None:
    return (await session.execute(
        select(Enquiry).where(Enquiry.whatsapp_contact_id == contact_id, Enquiry.status.in_(OPEN_STATUSES))
        .order_by(Enquiry.created_at.desc(), Enquiry.id.desc()).limit(1)
    )).scalar_one_or_none()


async def link_enquiry(session: AsyncSession, enquiry: Enquiry, contact_id: uuid.UUID, source: str, at: datetime) -> bool:
    """Link only an unlinked enquiry (or re-confirm the same contact): a reference never steals a chat already linked elsewhere."""
    if enquiry.whatsapp_contact_id not in (None, contact_id):
        return False
    if enquiry.whatsapp_contact_id is None:
        enquiry.whatsapp_contact_id, enquiry.linked_at, enquiry.link_source = contact_id, at, source
        await session.flush()
    return True


async def mark_contacted(session: AsyncSession, enquiry: Enquiry, paused_until: datetime) -> bool:
    """handed_off -> contacted, once; always (re)starts the bot pause. True only when the status actually changed."""
    changed = enquiry.status == "handed_off"
    if changed:
        enquiry.status = "contacted"
    enquiry.bot_paused_until = paused_until
    await session.flush()
    return changed


async def list_unlinked(session: AsyncSession, limit: int, cursor: tuple[datetime, uuid.UUID] | None) -> list[WhatsAppContact]:
    linked = exists().where(Enquiry.whatsapp_contact_id == WhatsAppContact.id)
    stmt = select(WhatsAppContact).where(~linked)
    if cursor:
        stmt = stmt.where(or_(WhatsAppContact.last_seen_at < cursor[0], and_(WhatsAppContact.last_seen_at == cursor[0], WhatsAppContact.id < cursor[1])))
    return list((await session.execute(stmt.order_by(WhatsAppContact.last_seen_at.desc(), WhatsAppContact.id.desc()).limit(limit))).scalars())


async def link_contact_by_staff(session: AsyncSession, contact_id: uuid.UUID, reference: str, at: datetime) -> Enquiry:
    enquiry = await enquiry_by_reference(session, reference)
    if enquiry is None:
        raise RepositoryError("Enquiry not found")
    if not await link_enquiry(session, enquiry, contact_id, "staff", at):
        raise RepositoryError("Enquiry is already linked to another chat")
    # Backfill the contact's earlier unlinked messages so the timeline is complete.
    await session.execute(update(WhatsAppMessage).where(WhatsAppMessage.contact_id == contact_id, WhatsAppMessage.enquiry_id.is_(None))
                          .values(enquiry_id=enquiry.id))
    return enquiry


async def timeline(session: AsyncSession, enquiry_id: uuid.UUID, limit: int) -> list[WhatsAppMessage]:
    rows = (await session.execute(select(WhatsAppMessage).where(WhatsAppMessage.enquiry_id == enquiry_id)
                                  .order_by(WhatsAppMessage.sent_at.desc(), WhatsAppMessage.id.desc()).limit(limit))).scalars()
    return list(reversed(list(rows)))


async def contact_exists(session: AsyncSession, contact_id: uuid.UUID) -> bool:
    return (await session.execute(select(exists().where(WhatsAppContact.id == contact_id)))).scalar_one()


async def contact_by_chat(session: AsyncSession, chat: str) -> WhatsAppContact | None:
    return (await session.execute(select(WhatsAppContact).where(WhatsAppContact.chat_jid == chat))).scalar_one_or_none()


async def _latest_at(session: AsyncSession, contact_id: uuid.UUID, sent_by: str) -> datetime | None:
    return (await session.execute(select(func.max(WhatsAppMessage.sent_at)).where(WhatsAppMessage.contact_id == contact_id, WhatsAppMessage.sent_by == sent_by))).scalar_one()


async def last_staff_at(session: AsyncSession, contact_id: uuid.UUID) -> datetime | None:
    return await _latest_at(session, contact_id, "staff")


async def last_bot_at(session: AsyncSession, contact_id: uuid.UUID) -> datetime | None:
    return await _latest_at(session, contact_id, "bot")


async def bot_wrote_for_enquiry(session: AsyncSession, enquiry_id: uuid.UUID) -> bool:
    return (await session.execute(select(exists().where(WhatsAppMessage.enquiry_id == enquiry_id, WhatsAppMessage.sent_by == "bot")))).scalar_one()


async def verify_items(session: AsyncSession, items: list[dict]) -> list[dict]:
    """Re-check a stored enquiry snapshot against the live catalogue (same rules as create_enquiry). Empty = unchanged."""
    ids = [uuid.UUID(i["variant_id"]) for i in items]
    live = {v.id: (v, p) for v, p in (await session.execute(select(Variant, Product).join(Product, Product.id == Variant.product_id).where(Variant.id.in_(ids)))).all()}
    issues = []
    for item in items:
        found = live.get(uuid.UUID(item["variant_id"]))
        base = {"variant_id": item["variant_id"]}
        if not found or found[1].status != "active" or not found[1].is_active or not found[0].is_active:
            issues.append({**base, "reason": "unavailable"})
        elif found[0].stock < 1:
            issues.append({**base, "reason": "out_of_stock"})
        elif item["quantity"] > found[0].stock:
            issues.append({**base, "reason": "insufficient_stock", "available": found[0].stock})
        elif item["unit_price"] != found[0].price:
            issues.append({**base, "reason": "price_changed", "current_price": found[0].price, "current_currency": found[0].currency})
    return issues
