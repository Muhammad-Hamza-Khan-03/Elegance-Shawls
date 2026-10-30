"""POST /v1/assistant/actions/execute: the only place an assistant proposal can take effect, and only on explicit user confirmation.

add_to_cart returns the server-verified line for the browser to put in its own cart (the cart is client state); the enquiry action
creates a reference through the existing enquiry repository. Neither sends a message, orders, charges or reserves stock.
"""
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from actions import executor as x
from actions import kernel as k
from assistant.stream import SERVER_PERMISSIONS  # never taken from the client
from database.pg import get_pg_session
from repositories import enquiries as repo
from repositories.enquiries import Line

router = APIRouter(prefix="/v1/assistant/actions", tags=["Assistant"])
_LEDGER = x.ExecutionLedger()


def get_ledger() -> x.ExecutionLedger:
    return _LEDGER


class ExecuteRequest(BaseModel):
    session_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    idempotency_key: str = Field(pattern=r"^idem_[A-Za-z0-9_-]{16,64}$")
    action_type: Literal["add_to_cart", "start_whatsapp_enquiry"]
    confirmed: Literal[True]
    params: dict[str, Any]


def _lines(params: dict) -> list[dict]:
    return params["items"] if "items" in params else [params]


@router.post("/execute")
async def execute(body: ExecuteRequest, session: AsyncSession = Depends(get_pg_session), ledger: x.ExecutionLedger = Depends(get_ledger)):
    proposal = k.ActionProposal(body.action_type, body.idempotency_key, body.params, k.ActionContext(body.session_id, SERVER_PERMISSIONS))
    catalogue: dict = {}

    async def load() -> k.InMemoryCatalogue:
        ids = []
        for line in _lines(body.params) if isinstance(body.params, dict) else []:
            try:
                ids.append(uuid.UUID(str(line.get("product_id"))))
            except (ValueError, AttributeError):
                pass  # the kernel rejects malformed params
        catalogue.update(await repo.catalogue_snapshot(session, ids[:k.MAX_LINES]))
        return k.InMemoryCatalogue(catalogue)

    async def perform(action: k.ActionType, params: dict) -> dict:
        lines = _lines(params)
        items = [{"product_id": l["product_id"], "variant_id": l["variant_id"], "quantity": l["quantity"],
                  "slug": catalogue[l["product_id"]]["slug"]} for l in lines]
        if action is k.ActionType.ADD_TO_CART:
            return {"items": items}
        enquiry = await repo.create_enquiry(session, [
            Line(uuid.UUID(l["product_id"]), uuid.UUID(l["variant_id"]), l["quantity"], l["expected_unit_price"], l["currency"]) for l in lines])
        return {"reference": enquiry.reference, "items": items, "total": enquiry.total, "currency": enquiry.currency}

    async with session.begin():
        out = await x.execute(proposal, confirmed=body.confirmed, load_catalogue=load, perform=perform, ledger=ledger)
    if out.outcome != "executed":
        raise HTTPException(status_code=409, detail={"status": "rejected", "reason": out.reason})
    return {"status": "executed", "action_type": out.action_type, "replayed": out.replayed, "result": out.result}
