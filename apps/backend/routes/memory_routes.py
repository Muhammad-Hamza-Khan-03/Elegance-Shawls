"""/v1/me/memory: a customer's own explicit memory (M4-S1). The customer is always the authenticated principal, never a path,
query or body value. One transaction per request, committed here after the provider returns; a refusal rolls everything back.

`memory_customer` resolves the customer from a server-verified session (memory/principal.py). Customer authentication is
configuration-gated and disabled by default; without a verifier every request is 401. Tests override the verifier or principal.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from memory.principal import CustomerPrincipal, current_principal
from memory.provider import MemoryProvider, get_memory_provider
from memory.service import MemoryRejected
from schemas.memory_schema import ConsentRequest, ConsentResponse, MemoryCreate, MemoryItemOut, MemoryList, MemoryUpdate

router = APIRouter(prefix="/v1/me/memory", tags=["Memory"])


async def memory_customer(principal: CustomerPrincipal = Depends(current_principal)) -> uuid.UUID:
    return principal.customer_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _run(provider: MemoryProvider, work):
    try:
        result = await work
        await provider.commit()
        return result
    except MemoryRejected as exc:
        await provider.rollback()
        raise HTTPException(exc.status, {"status": "rejected", "reason": exc.reason}) from exc
    except BaseException:
        await provider.rollback()
        raise


@router.get("/consent", response_model=ConsentResponse)
async def read_consent(customer: uuid.UUID = Depends(memory_customer), provider: MemoryProvider = Depends(get_memory_provider)):
    return await _run(provider, provider.get_consent(customer))


@router.put("/consent", response_model=ConsentResponse)
async def write_consent(body: ConsentRequest, customer: uuid.UUID = Depends(memory_customer), provider: MemoryProvider = Depends(get_memory_provider)):
    return await _run(provider, provider.set_consent(customer, body.granted, _now()))


@router.get("", response_model=MemoryList)
async def list_memory(customer: uuid.UUID = Depends(memory_customer), provider: MemoryProvider = Depends(get_memory_provider)):
    return {"items": await _run(provider, provider.list_items(customer, _now()))}


@router.post("", response_model=MemoryItemOut)
async def create_memory(body: MemoryCreate, response: Response, customer: uuid.UUID = Depends(memory_customer),
                        provider: MemoryProvider = Depends(get_memory_provider)):
    item, replayed = await _run(provider, provider.create(customer, body, _now()))
    response.status_code = 200 if replayed else 201
    return item


@router.get("/{item_id}", response_model=MemoryItemOut)
async def read_memory(item_id: uuid.UUID, customer: uuid.UUID = Depends(memory_customer), provider: MemoryProvider = Depends(get_memory_provider)):
    return await _run(provider, provider.get_item(customer, item_id, _now()))


@router.patch("/{item_id}", response_model=MemoryItemOut)
async def update_memory(item_id: uuid.UUID, body: MemoryUpdate, customer: uuid.UUID = Depends(memory_customer),
                        provider: MemoryProvider = Depends(get_memory_provider)):
    return await _run(provider, provider.update(customer, item_id, body, _now()))


@router.delete("/{item_id}", status_code=204)
async def delete_memory(item_id: uuid.UUID, customer: uuid.UUID = Depends(memory_customer), provider: MemoryProvider = Depends(get_memory_provider)):
    await _run(provider, provider.delete(customer, item_id, _now()))
    return Response(status_code=204)


@router.delete("", status_code=200)
async def delete_all_memory(customer: uuid.UUID = Depends(memory_customer), provider: MemoryProvider = Depends(get_memory_provider)):
    return {"deleted": await _run(provider, provider.delete_all(customer, _now()))}
