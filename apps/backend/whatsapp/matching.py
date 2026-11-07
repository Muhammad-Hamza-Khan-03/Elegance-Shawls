"""Pure helpers (no I/O): enquiry reference extraction and the inbound event contract."""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# References are ES- plus 6 characters today; the database check allows 6-12.
REFERENCE_RE = re.compile(r"\bES-[A-Z0-9]{6,12}\b", re.IGNORECASE)
OPEN_STATUSES = ("handed_off", "contacted")


class InboundEvent(BaseModel):
    """Schema v1 of the `wa:inbound` stream entry; mirrors apps/whatsapp-bridge/schema/inbound-event.v1.json."""
    model_config = ConfigDict(extra="forbid")
    v: Literal[1]
    wa_id: str = Field(min_length=1, max_length=128)
    chat: str = Field(min_length=1, max_length=128)
    lid: str | None = Field(default=None, max_length=128)
    from_me: bool
    type: Literal["text", "image", "audio", "video", "document", "other"]
    text: str | None = Field(default=None, max_length=8192)
    quoted_id: str | None = Field(default=None, max_length=128)
    media: str | None = Field(default=None, max_length=512)
    push_name: str | None = Field(default=None, max_length=256)
    via_bot: bool = False       # set by the bridge for messages it sent on the bot's behalf
    ts: datetime


def extract_reference(text: str | None) -> str | None:
    found = REFERENCE_RE.search(text or "")
    return found.group(0).upper() if found else None


def phone_from_jid(chat: str) -> str | None:
    """+E.164 for a classic user JID (`9230012345@s.whatsapp.net`); None for @lid or anything else."""
    number, _, domain = chat.partition("@")
    return f"+{number}" if domain == "s.whatsapp.net" and number.isdigit() else None
