"""POST /v1/assistant/stream: off unless ASSISTANT_STREAM_ENABLED is true. Fake provider only; proposals, never execution."""
import os

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from assistant.stream import STREAM_HEADER, fake_provider, run

router = APIRouter(prefix="/v1/assistant", tags=["Assistant"])


class StreamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    message: str = Field(min_length=1, max_length=500)


def assistant_enabled() -> bool:
    return os.getenv("ASSISTANT_STREAM_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def get_provider():
    return fake_provider  # the only provider; tests override this dependency


@router.post("/stream")
async def stream(body: StreamRequest, provider=Depends(get_provider)):
    if not assistant_enabled():
        return JSONResponse({"enabled": False, "error": "assistant_disabled"}, status_code=503,
                            headers={"cache-control": "no-store"})
    return StreamingResponse(run(provider, body.message, body.session_id), media_type="text/event-stream",
                             headers={"cache-control": "no-store", "x-accel-buffering": "no", **STREAM_HEADER})
