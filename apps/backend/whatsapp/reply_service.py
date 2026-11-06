"""Glue for automated replies: gather facts, decide (replies.py), persist side effects, ask the bridge to deliver.

The bridge enforces its own safety (24-hour customer-opened guard, send cap, idempotency); this layer never sends to a chat
that has not just written to us because it only runs for an inbound message.
"""
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from repositories import admin as admin_repo, whatsapp as repo
from whatsapp import replies
from whatsapp.matching import InboundEvent, extract_reference, phone_from_jid

logger = logging.getLogger("whatsapp.replies")


class SendRefused(Exception):
    """The bridge declined permanently (4xx): do not retry."""


class BridgeSender:
    async def send(self, chat: str, text: str, key: str) -> str:
        """Returns the WhatsApp message id of the sent message."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                reply = await client.post(f"{settings.whatsapp_bridge_url}/send", json={"chat": chat, "text": text, "idempotency_key": key},
                                          headers={"Authorization": f"Bearer {settings.whatsapp_bridge_token}"})
        except httpx.HTTPError as exc:
            raise RuntimeError(f"bridge unreachable: {exc}") from exc
        if 400 <= reply.status_code < 500:
            raise SendRefused(f"{reply.status_code} {reply.text[:200]}")
        reply.raise_for_status()
        return reply.json()["wa_id"]


def allowlisted(chat: str) -> bool:
    allowed = {re.sub(r"\D", "", n) for n in settings.whatsapp_reply_allowlist.split(",") if re.sub(r"\D", "", n)}
    if not allowed:
        return True
    phone = phone_from_jid(chat)               # @lid chats have no number: not allowlisted while a list is set
    return bool(phone) and phone.lstrip("+") in allowed


async def _prepare(session: AsyncSession, event: InboundEvent, now: datetime):
    contact = await repo.contact_by_chat(session, event.chat)
    if contact is None:
        return None
    window = timedelta(hours=settings.whatsapp_bot_pause_hours)
    enquiry = await repo.open_enquiry_for_contact(session, contact.id)
    staff_at, bot_at = await repo.last_staff_at(session, contact.id), await repo.last_bot_at(session, contact.id)
    paused = bool(staff_at and now - staff_at < window) or bool(enquiry and enquiry.bot_paused_until and enquiry.bot_paused_until > now)
    summary_sent = bool(enquiry and await repo.bot_wrote_for_enquiry(session, enquiry.id))
    reference = extract_reference(event.text)
    details = dict((enquiry.customer_details or {}) if enquiry else {})
    facts = replies.Facts(
        now=now, event_ts=event.ts, text=event.text, max_age=timedelta(seconds=settings.whatsapp_reply_max_age_seconds),
        allowlisted=allowlisted(event.chat), paused=paused, bot_recent=bool(bot_at and now - bot_at < window),
        reference_in_message=bool(reference and enquiry and reference == enquiry.reference), has_enquiry=enquiry is not None,
        summary_sent=summary_sent, details={k: v for k, v in details.items() if k in replies.FIELDS},
        issues=tuple(await repo.verify_items(session, enquiry.items)) if enquiry and not summary_sent else ())
    return contact, enquiry, facts


async def maybe_reply(sessions, event: InboundEvent, sender, now: datetime | None = None) -> str | None:
    """Reply to one inbound customer message if the rules allow. Safe to call again for the same event (idempotency key)."""
    if event.from_me:
        return None
    now = now or datetime.now(timezone.utc)
    ts = event.ts if event.ts.tzinfo else event.ts.replace(tzinfo=timezone.utc)
    event = event.model_copy(update={"ts": ts})
    async with sessions() as session, session.begin():
        prepared = await _prepare(session, event, now)
        decision = replies.decide(prepared[2]) if prepared else None
        if decision is None:
            return None
        contact, enquiry, facts = prepared
        if enquiry is not None:
            details = dict(enquiry.customer_details or {})
            details.update(decision.save_details or {})
            if decision.flag:
                details["staff_flag"] = decision.flag
            if details != (enquiry.customer_details or {}):
                enquiry.customer_details = details
        text = replies.render(decision, lang=replies.language(event.text), reference=enquiry.reference if enquiry else "",
                              items=enquiry.items if enquiry else [], total=enquiry.total if enquiry else 0,
                              currency=enquiry.currency if enquiry else "PKR", issues=facts.issues)
        target = enquiry.reference if enquiry else event.chat
        enquiry_id = enquiry.id if enquiry else None
    wa_id = await sender.send(event.chat, text, f"reply-{event.wa_id}")   # raises: the stream entry is retried (key makes it safe)
    async with sessions() as session, session.begin():
        # Stored now, not only when the bridge echoes it, so a customer's very next message already sees the bot has written.
        await repo.insert_message(session, wa_message_id=wa_id, contact_id=contact.id, direction="out", from_me=True, type="text", text=text,
                                  sent_by="bot", enquiry_id=enquiry_id, sent_at=datetime.now(timezone.utc))
        await admin_repo.add_audit(session, actor_type="system", actor_id="system:whatsapp-bot", action="whatsapp.bot_reply",
                                   target=target, outcome="success", detail={"kind": decision.kind, "in_reply_to": event.wa_id})
    return decision.kind
