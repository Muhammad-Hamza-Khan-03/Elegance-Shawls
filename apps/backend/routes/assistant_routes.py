"""POST /v1/assistant/stream: local, bounded SSE chat with the deterministic fake assistant (no model, network or side effects)."""
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from assistant.stream import demo_catalogue, fake_provider, stream_events

router = APIRouter(prefix="/v1/assistant", tags=["Assistant"])

Scalar = str | int | bool | None


class StreamRequest(BaseModel):
    session_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    idempotency_key: str = Field(pattern=r"^idem_[A-Za-z0-9_-]{16,64}$")
    message: str = Field(min_length=1, max_length=500)
    context: dict[str, Scalar] = Field(default_factory=dict)

    @field_validator("context")
    @classmethod
    def _bounded(cls, ctx: dict[str, Scalar]) -> dict[str, Scalar]:
        if len(ctx) > 10 or any(len(key) > 40 or (isinstance(v, str) and len(v) > 200) for key, v in ctx.items()):
            raise ValueError("context too large")
        return ctx


def get_provider():
    return fake_provider  # the only provider; tests override this dependency


@router.post("/stream")
async def stream(body: StreamRequest, request: Request, provider=Depends(get_provider)):
    events: AsyncIterator[str] = stream_events(
        provider(body.message, body.idempotency_key), session_id=body.session_id, context=body.context,
        idempotency_key=body.idempotency_key, catalogue=demo_catalogue(), is_disconnected=request.is_disconnected)
    return StreamingResponse(events, media_type="text/event-stream",
                             headers={"cache-control": "no-store", "x-accel-buffering": "no"})
