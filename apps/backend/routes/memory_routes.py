"""/v1/me/memory: a customer's own explicit memory (M4-S1). The customer is always the authenticated principal, never a path,
query or body value. One transaction per request, committed here after the service returns; a refusal rolls everything back.

`memory_customer` resolves the customer from a server-verified session (memory/principal.py). No customer authentication exists yet,
so no verifier is installed and every request is 401 until one is. Tests override `memory_customer` or the verifier.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from database.pg import get_pg_session
from memory import service
from memory.principal import CustomerPrincipal, current_principal
from memory.service import MemoryRejected
from schemas.memory_schema import ConsentRequest, ConsentResponse, MemoryCreate, MemoryItemOut, MemoryList, MemoryUpdate

router = APIRouter(prefix="/v1/me/memory", tags=["Memory"])


async def memory_customer(principal: CustomerPrincipal = Depends(current_principal)) -> uuid.UUID:
    return principal.customer_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _run(session: AsyncSession, work):
    try:
        result = await work
        await session.commit()
        return result
    except MemoryRejected as exc:
        await session.rollback()
        raise HTTPException(exc.status, {"status": "rejected", "reason": exc.reason}) from exc
    except BaseException:
        await session.rollback()
        raise


@router.get("/consent", response_model=ConsentResponse)
async def read_consent(customer: uuid.UUID = Depends(memory_customer), session: AsyncSession = Depends(get_pg_session)):
    return await _run(session, service.get_consent(session, customer))


@router.put("/consent", response_model=ConsentResponse)
async def write_consent(body: ConsentRequest, customer: uuid.UUID = Depends(memory_customer), session: AsyncSession = Depends(get_pg_session)):
    return await _run(session, service.set_consent(session, customer, body.granted, _now()))


@router.get("", response_model=MemoryList)
async def list_memory(customer: uuid.UUID = Depends(memory_customer), session: AsyncSession = Depends(get_pg_session)):
    return {"items": await _run(session, service.list_items(session, customer, _now()))}


@router.post("", response_model=MemoryItemOut)
async def create_memory(body: MemoryCreate, response: Response, customer: uuid.UUID = Depends(memory_customer),
                        session: AsyncSession = Depends(get_pg_session)):
    item, replayed = await _run(session, service.create(session, customer, body, _now()))
    response.status_code = 200 if replayed else 201
    return item


@router.get("/{item_id}", response_model=MemoryItemOut)
async def read_memory(item_id: uuid.UUID, customer: uuid.UUID = Depends(memory_customer), session: AsyncSession = Depends(get_pg_session)):
    return await _run(session, service.get_item(session, customer, item_id, _now()))


@router.patch("/{item_id}", response_model=MemoryItemOut)
async def update_memory(item_id: uuid.UUID, body: MemoryUpdate, customer: uuid.UUID = Depends(memory_customer),
                        session: AsyncSession = Depends(get_pg_session)):
    return await _run(session, service.update(session, customer, item_id, body, _now()))


@router.delete("/{item_id}", status_code=204)
async def delete_memory(item_id: uuid.UUID, customer: uuid.UUID = Depends(memory_customer), session: AsyncSession = Depends(get_pg_session)):
    await _run(session, service.delete(session, customer, item_id, _now()))
    return Response(status_code=204)


@router.delete("", status_code=200)
async def delete_all_memory(customer: uuid.UUID = Depends(memory_customer), session: AsyncSession = Depends(get_pg_session)):
    return {"deleted": await _run(session, service.delete_all(session, customer, _now()))}
