"""Catalogue assistant for WhatsApp ("Later" in the plan). Deterministic: the M2 parser turns words into hard filters, the live
catalogue is searched, and products, prices and stock come from the database. No LLM is ever called for this channel
(assistant.grounded.llm_blocked): chats are personal data and the section 19.2 privacy gate is not passed for them.
"""
import hashlib
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from assistant import grounded, personal
from configuration.config import settings
from repositories import whatsapp as repo
from voice.bridge import bridge_voice_transcript
from whatsapp.matching import InboundEvent
from whatsapp.replies import _templates, language

MAX_REPLY_CHARS = 1500


def _variant(product: dict) -> dict | None:
    return next((v for v in product.get("variants", []) if v["is_active"] is True and (v["stock"] or 0) > 0 and v["price"] is not None), None)


def _card(product: dict) -> str:
    v = _variant(product)
    link = f" {settings.whatsapp_site_url.rstrip('/')}/product/{product['slug']}" if settings.whatsapp_site_url and product.get("slug") else ""
    if v is None:
        return f"• {product['name']}: out of stock{link}"
    colour = f" ({v['color']})" if v.get("color") else ""
    return f"• {product['name']}{colour}: {v['currency']} {v['price']:,}{link}"


def voice_trusted(text: str) -> bool:
    """A transcribed voice note may be used to browse, never to act. The voice contract's price-or-negation check still fails closed
    for a negated or ambiguous request ("not red", two different prices); merely lacking a price is fine for browsing, and this
    channel proposes no cart or order action anyway."""
    reasons = bridge_voice_transcript(text, provenance="whatsapp_asr").reasons
    return not {"voice_negation", "voice_ambiguous", "invalid_transcript"} & set(reasons)


async def answer(session: AsyncSession, event: InboundEvent, contact_id, now: datetime) -> str | None:
    """The reply text, or None when the assistant has nothing grounded to say (the caller sends the holding reply instead)."""
    text = (event.text or "").strip()
    if not text or personal.remember_request(text) is not None or personal.is_recall(text):
        return None                                   # memory is a signed-in web feature; never offered over WhatsApp
    if event.type == "audio" and not voice_trusted(text):
        return "I was not sure I heard that correctly. Could you say it again, or type it instead?"
    history = await repo.recent_customer_texts(session, contact_id, event.wa_id, now - timedelta(hours=24))
    key = "idem_" + hashlib.sha256(event.wa_id.encode()).hexdigest()[:24]
    token = grounded.llm_blocked.set(True)
    try:
        chunks, catalogue = await grounded.ground(session, text, key, voice=False, principal=None, history=tuple(history))
        parts, ids = [], []
        async for chunk in chunks:
            if chunk.get("type") == "text":
                parts.append(chunk["delta"])
            elif chunk.get("type") == "product":
                ids.append(chunk["product_id"])
    finally:
        grounded.llm_blocked.reset(token)
    cards = [_card(p) for pid in ids if (p := catalogue.get(pid))]
    body = " ".join("".join(parts).split())
    if not body and not cards:
        return None
    t = _templates()[language(text)]
    lines = [body, *cards] if cards else [body]
    if cards:
        lines.append(t["assistant_footer"])
    return "\n".join(line for line in lines if line)[:MAX_REPLY_CHARS]
