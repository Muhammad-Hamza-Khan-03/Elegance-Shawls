"""POST /v1/assistant/actions/execute: off unless ASSISTANT_ACTIONS_ENABLED is true. Confirmed proposals only; sends/orders nothing."""
import os
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from actions import execution as x
from actions import kernel as k
from database.pg import get_pg_session

router = APIRouter(prefix="/v1/assistant/actions", tags=["Assistant"])
NO_STORE = {"cache-control": "no-store"}


class ConfirmationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    session_id: str
    fingerprint: str
    confirmed_at: float
    expires_at: float
    explicit: bool


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    name: str
    session_id: str
    params: dict[str, Any]
    constraints: dict[str, Any] = Field(default_factory=lambda: {"hard": {}})
    confirmation: ConfirmationIn | None = None


def actions_enabled() -> bool:
    return os.getenv("ASSISTANT_ACTIONS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


@router.post("/execute")
async def execute(body: ExecuteRequest, session: AsyncSession = Depends(get_pg_session)):
    if not actions_enabled():
        return JSONResponse({"enabled": False, "error": "actions_disabled"}, status_code=503, headers=NO_STORE)
    proposal = k.ActionProposal(body.action_id, body.name, body.session_id, body.params, body.constraints,
                                k.Confirmation(**body.confirmation.model_dump()) if body.confirmation else None)

    async def available(lines):
        return await x.lines_available(session, lines)

    async with session.begin():
        out = await x.execute(proposal, store=x.PgStore(session), check_lines=available)
    if out.status != "executed":
        code = 409 if out.reason == "idempotency_conflict" else 422
        return JSONResponse({"status": "rejected", "reason": out.reason, "action_id": out.action_id}, status_code=code, headers=NO_STORE)
    return JSONResponse({"status": "executed", "action": out.action, "action_id": out.action_id, "replayed": out.replayed,
                         "acknowledged": True, "intent": out.result["intent"]}, headers=NO_STORE)
