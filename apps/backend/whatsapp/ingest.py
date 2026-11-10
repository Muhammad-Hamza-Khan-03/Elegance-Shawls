"""Store one inbound event exactly once, link it to an enquiry, and move the enquiry to `contacted`. No Redis, no sending."""
from datetime import timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from repositories import admin as admin_repo, whatsapp as repo
from whatsapp.matching import InboundEvent, extract_reference, phone_from_jid


async def ingest(session: AsyncSession, event: InboundEvent) -> bool:
    """Caller owns the transaction. Returns False for a redelivered message (nothing changes)."""
    if await repo.message_exists(session, event.wa_id):
        return False
    sent_at = event.ts if event.ts.tzinfo else event.ts.replace(tzinfo=timezone.utc)
    contact = await repo.upsert_contact(session, chat=event.chat, lid=event.lid, phone=phone_from_jid(event.chat),
                                        name=None if event.from_me else event.push_name, seen_at=sent_at)

    enquiry = None
    reference = None if event.from_me else extract_reference(event.text)
    if reference:
        candidate = await repo.enquiry_by_reference(session, reference)
        if candidate and await repo.link_enquiry(session, candidate, contact.id, "reference", sent_at):
            enquiry = candidate
    if enquiry is None:
        enquiry = await repo.open_enquiry_for_contact(session, contact.id)

    stored = await repo.insert_message(
        session, wa_message_id=event.wa_id, contact_id=contact.id, direction="out" if event.from_me else "in", from_me=event.from_me,
        type=event.type, text=event.text, sent_by="bot" if event.via_bot else "staff" if event.from_me else "customer", quoted_wa_id=event.quoted_id,
        media_ref=event.media, enquiry_id=enquiry.id if enquiry else None, sent_at=sent_at)
    if stored and event.from_me and not event.via_bot and enquiry is not None:   # the bot's own echo is not staff
        paused_until = sent_at + timedelta(hours=settings.whatsapp_bot_pause_hours)
        if await repo.mark_contacted(session, enquiry, paused_until):
            await admin_repo.add_audit(session, actor_type="system", actor_id="system:whatsapp", action="enquiry.contacted",
                                       target=enquiry.reference, outcome="success", detail={"source": "staff_reply"})
    return stored
