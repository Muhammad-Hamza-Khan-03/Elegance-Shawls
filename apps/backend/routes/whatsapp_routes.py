"""WhatsApp bridge admin API. Every admin route answers 503 `whatsapp_disabled` unless WHATSAPP_BRIDGE_ENABLED=true."""
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from database.pg import get_pg_session
from database.redis_client import get_redis
from repositories import RepositoryError, enquiries as enquiry_repo, whatsapp as repo
from security.admin_auth import PLATFORM_OPERATE, require_admin, require_permission
from utils.pagination import decode_cursor, encode_cursor
from whatsapp import config as wa_config, monitoring


def require_enabled() -> None:
    if not wa_config.is_enabled():
        raise HTTPException(status_code=503, detail={"code": "whatsapp_disabled"})


async def _bridge(method: str, path: str, body: dict | None = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            reply = await client.request(method, f"{settings.whatsapp_bridge_url}{path}", json=body,
                                         headers={"Authorization": f"Bearer {settings.whatsapp_bridge_token}"})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="The WhatsApp bridge is unreachable") from exc
    if reply.status_code >= 400:
        raise HTTPException(status_code=409 if reply.status_code < 500 else 502, detail=reply.json().get("error", "Bridge error") if reply.content else "Bridge error")
    return reply.json()


public_router = APIRouter(prefix="/v1/whatsapp", tags=["WhatsApp"])
admin_router = APIRouter(prefix="/v1/admin", tags=["WhatsApp"], dependencies=[Depends(require_admin), Depends(require_enabled)])


@public_router.get("/mode")
async def mode():
    """Lets the storefront vary copy at runtime; deliberately not a NEXT_PUBLIC_ build-time variable."""
    return {"mode": "automated" if wa_config.is_enabled() else "link"}


# Pairing hands out a login credential (the QR): owner/operate permission only, audited by the guard on every mutation.
pairing_router = APIRouter(prefix="/v1/admin/whatsapp/pairing", tags=["WhatsApp"],
                           dependencies=[Depends(require_permission(PLATFORM_OPERATE)), Depends(require_enabled)])


class PairingCode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str = Field(pattern=r"^[0-9]{8,15}$")


@pairing_router.get("")
async def pairing_status():
    return await _bridge("GET", "/pairing/status")


@pairing_router.post("")
async def pairing_start():
    return await _bridge("POST", "/pairing/start")


@pairing_router.post("/code")
async def pairing_code(payload: PairingCode):
    return await _bridge("POST", "/pairing/code", {"phone": payload.phone})


@pairing_router.delete("")
async def pairing_disconnect():
    return await _bridge("POST", "/pairing/disconnect")


class LinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_id: uuid.UUID
    enquiry_reference: str = Field(min_length=1, max_length=20)


@admin_router.get("/whatsapp/status")
async def status(session: AsyncSession = Depends(get_pg_session)):
    problem = wa_config.misconfiguration()
    if problem:
        return {"state": "misconfigured", "detail": problem, "alerts": []}
    bridge: dict = {"state": "unreachable"}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            reply = await client.get(f"{settings.whatsapp_bridge_url}/health", headers={"Authorization": f"Bearer {settings.whatsapp_bridge_token}"})
            reply.raise_for_status()
            bridge = reply.json()
    except (httpx.HTTPError, ValueError):
        pass
    snap = await monitoring.collect(session, get_redis())
    return {**bridge, "state": snap.state, "stream_lag": snap.lag, "dead_letters": snap.dead, "alerts": snap.alerts,
            "ingested_last_hour": snap.ingested_last_hour, "linked_by_reference": snap.linked_by_reference,
            "linked_by_staff": snap.linked_by_staff, "median_contact_seconds": snap.median_contact_seconds}


def _contact(c) -> dict:
    return {"id": str(c.id), "phone": c.phone_e164, "display_name": c.display_name, "first_seen_at": c.first_seen_at, "last_seen_at": c.last_seen_at}


@admin_router.get("/whatsapp/unlinked")
async def unlinked(limit: int = Query(default=50, ge=1, le=100), cursor: str | None = Query(default=None),
                   session: AsyncSession = Depends(get_pg_session)):
    try:
        key = decode_cursor(cursor) if cursor else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc
    rows = await repo.list_unlinked(session, limit + 1, key)
    page = rows[:limit]
    return {"items": [_contact(c) for c in page],
            "next_cursor": encode_cursor(page[-1].last_seen_at, page[-1].id) if len(rows) > limit else None}


@admin_router.post("/whatsapp/link")
async def link(payload: LinkRequest, session: AsyncSession = Depends(get_pg_session)):
    try:
        async with session.begin():
            if not await repo.contact_exists(session, payload.contact_id):
                raise HTTPException(status_code=404, detail="Chat not found")
            enquiry = await repo.link_contact_by_staff(session, payload.contact_id, payload.enquiry_reference, datetime.now(timezone.utc))
            return {"reference": enquiry.reference, "link_source": enquiry.link_source}
    except RepositoryError as exc:
        raise HTTPException(status_code=409 if "linked" in str(exc) else 404, detail=str(exc)) from exc


@admin_router.get("/enquiries/{reference}/whatsapp")
async def enquiry_timeline(reference: str, limit: int = Query(default=200, ge=1, le=500), session: AsyncSession = Depends(get_pg_session)):
    enquiry = await enquiry_repo.get_by_reference(session, reference)
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    messages = await repo.timeline(session, enquiry.id, limit)
    return {"reference": enquiry.reference, "status": enquiry.status, "items": [
        {"id": str(m.id), "sent_by": m.sent_by, "type": m.type, "text": m.text, "sent_at": m.sent_at} for m in messages]}


class StatusMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template: str = Field(pattern=r"^(confirmed|dispatched)$")
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")


@admin_router.post("/enquiries/{reference}/whatsapp/message")
async def send_status_message(reference: str, payload: StatusMessage, session: AsyncSession = Depends(get_pg_session)):
    """Staff-triggered fixed status text, sent only inside a chat the customer opened (the bridge enforces the 24-hour rule).
    This is how an order is ever called confirmed: a person presses the button; the automatic replies never say it."""
    from whatsapp import replies
    from whatsapp.reply_service import BridgeSender, SendRefused

    async with session.begin():
        enquiry = await enquiry_repo.get_by_reference(session, reference)
        if not enquiry or enquiry.whatsapp_contact_id is None:
            raise HTTPException(status_code=404, detail="Enquiry is not linked to a WhatsApp chat")
        contact_id = enquiry.whatsapp_contact_id
        chat = (await repo.contact_chat(session, contact_id))
        last_text = await repo.recent_customer_texts(session, contact_id, "", datetime(2000, 1, 1, tzinfo=timezone.utc), limit=1)
        text = replies._templates()[replies.language(last_text[-1] if last_text else None)][f"status_{payload.template}"].format(reference=enquiry.reference)
        ref = enquiry.reference
    try:
        wa_id = await BridgeSender().send(chat, text, f"status-{ref}-{payload.template}-{payload.idempotency_key}")
    except SendRefused as exc:
        raise HTTPException(status_code=409, detail="The customer has not written in the last 24 hours, so no message can be sent") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="The WhatsApp bridge is unreachable") from exc
    async with session.begin():
        now = datetime.now(timezone.utc)
        enquiry = await enquiry_repo.get_by_reference(session, ref)
        await repo.insert_message(session, wa_message_id=wa_id, contact_id=contact_id, direction="out", from_me=True, type="text", text=text,
                                  sent_by="staff", enquiry_id=enquiry.id, sent_at=now)
        await repo.mark_contacted(session, enquiry, now + timedelta(hours=settings.whatsapp_bot_pause_hours))   # a person is handling this chat
    return {"sent": True, "template": payload.template}
