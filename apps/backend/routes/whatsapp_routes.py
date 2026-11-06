"""WhatsApp bridge admin API. Every admin route answers 503 `whatsapp_disabled` unless WHATSAPP_BRIDGE_ENABLED=true."""
import uuid
from datetime import datetime, timezone

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
from whatsapp import config as wa_config


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
async def status():
    problem = wa_config.misconfiguration()
    if problem:
        return {"state": "misconfigured", "detail": problem}
    bridge: dict = {"state": "unreachable"}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            reply = await client.get(f"{settings.whatsapp_bridge_url}/health", headers={"Authorization": f"Bearer {settings.whatsapp_bridge_token}"})
            reply.raise_for_status()
            bridge = reply.json()
    except (httpx.HTTPError, ValueError):
        pass
    lag = None
    redis = get_redis()
    if redis is not None:
        try:
            groups = {g["name"]: g for g in await redis.xinfo_groups("wa:inbound")}
            lag = groups.get("backend", {}).get("lag")
        except Exception:
            pass
    return {**bridge, "stream_lag": lag}


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
