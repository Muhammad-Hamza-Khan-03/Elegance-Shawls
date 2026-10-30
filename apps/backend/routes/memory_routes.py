"""/v1/me/memory: a customer's own explicit memory (M4-S1). The customer is always the authenticated principal, never a path,
query or body value. One transaction per request, committed here after the service returns; a refusal rolls everything back.

Customer authentication does not exist yet (a later M4 slice wires it), so `memory_customer` refuses every request. Tests override
it; nothing can reach customer memory in a deployed app until real authentication replaces it.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from database.pg import get_pg_session
from memory import service
from memory.service import MemoryRejected
from schemas.memory_schema import ConsentRequest, ConsentResponse, MemoryCreate, MemoryItemOut, MemoryList, MemoryUpdate

router = APIRouter(prefix="/v1/me/memory", tags=["Memory"])


async def memory_customer() -> uuid.UUID:
    """shortcut: no customer authentication yet, so deny everything; replace with the real principal dependency when it exists."""
    raise HTTPException(401, "Customer authentication is required", headers={"WWW-Authenticate": "Session"})


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
