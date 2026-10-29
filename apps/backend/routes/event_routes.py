"""POST /v1/events: validated, size-capped batches of anonymous interaction events."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from database.pg import get_pg_session
from events.recorder import opted_out
from events.session import mint_session_token, verify_session_token
from models.relational_model import Event
from observability.tracing import scrub_text

router = APIRouter(prefix="/v1/events", tags=["Events"])

COOKIE = "es_sid"
MAX_PAYLOAD_KEYS = 10
MAX_STRING = 200
Scalar = str | int | float | bool | None


class EventIn(BaseModel):
    # Browsers may only report these; ui_action, voice and handoff are server-originated.
    type: Literal["view", "search", "impression", "click", "add_to_cart"]
    payload: dict[str, Scalar] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def _bounded(cls, payload: dict[str, Scalar]) -> dict[str, Scalar]:
        if len(payload) > MAX_PAYLOAD_KEYS:
            raise ValueError("too many payload keys")
        clean: dict[str, Scalar] = {}
        for key, value in payload.items():
            if len(key) > 40:
                raise ValueError("payload key too long")
            if isinstance(value, str):
                if len(value) > MAX_STRING:
                    raise ValueError("payload value too long")
                value = scrub_text(value)  # free-text search queries can contain contact details
            clean[key] = value
        return clean


class EventBatch(BaseModel):
    events: list[EventIn] = Field(min_length=1)


async def _read_limited(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.events_max_body_bytes:
        raise HTTPException(status_code=413, detail="Request body too large")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > settings.events_max_body_bytes:
            raise HTTPException(status_code=413, detail="Request body too large")
    return bytes(body)


@router.post("", status_code=202)
async def record_events(request: Request, response: Response, session: AsyncSession = Depends(get_pg_session)):
    if not settings.session_signing_key:
        raise HTTPException(status_code=503, detail="Event collection is not enabled")
    if opted_out(request):  # Do Not Track / Global Privacy Control: accept, store nothing, set no cookie
        return {"accepted": 0}
    try:
        batch = EventBatch.model_validate_json(await _read_limited(request))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=[{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]) from exc
    if len(batch.events) > settings.events_max_batch:
        raise HTTPException(status_code=422, detail=f"At most {settings.events_max_batch} events per batch")

    token = request.headers.get("x-session-token") or request.cookies.get(COOKIE)
    session_id = verify_session_token(token)
    if session_id is None:
        token = mint_session_token()
        session_id = verify_session_token(token)
    session.add_all(Event(session_id=session_id, type=e.type, payload=e.payload) for e in batch.events)
    await session.commit()

    response.set_cookie(COOKIE, token, max_age=30 * 24 * 3600, httponly=True, samesite="lax",
                        secure=settings.environment == "production")
    return {"accepted": len(batch.events), "session_token": token}
