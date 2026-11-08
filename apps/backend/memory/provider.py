"""Provider-neutral contract for explicit, customer-owned memory.

The caller supplies a customer id resolved from a server-verified session. A provider must enforce that id on every item
operation, consent before reads and writes, idempotency and tombstones, and content-free audit in the same transaction.
The PostgreSQL adapter delegates those rules to the existing memory service. No model or extraction provider is installed here.
"""
import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database.pg import get_pg_session
from memory import service
from schemas.memory_schema import MemoryCreate, MemoryItemOut, MemoryUpdate


@runtime_checkable
class MemoryProvider(Protocol):
    async def get_consent(self, customer_id: uuid.UUID) -> dict: ...
    async def set_consent(self, customer_id: uuid.UUID, granted: bool, now: datetime) -> dict: ...
    async def create(self, customer_id: uuid.UUID, req: MemoryCreate, now: datetime) -> tuple[MemoryItemOut, bool]: ...
    async def list_items(self, customer_id: uuid.UUID, now: datetime) -> list[MemoryItemOut]: ...
    async def get_item(self, customer_id: uuid.UUID, item_id: uuid.UUID, now: datetime) -> MemoryItemOut: ...
    async def update(self, customer_id: uuid.UUID, item_id: uuid.UUID, req: MemoryUpdate, now: datetime) -> MemoryItemOut: ...
    async def delete(self, customer_id: uuid.UUID, item_id: uuid.UUID, now: datetime) -> bool: ...
    async def delete_all(self, customer_id: uuid.UUID, now: datetime) -> int: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class PostgresMemoryProvider:
    """Current provider; the request owns one transaction and commits only after the operation succeeds."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_consent(self, customer_id: uuid.UUID) -> dict:
        return await service.get_consent(self._session, customer_id)

    async def set_consent(self, customer_id: uuid.UUID, granted: bool, now: datetime) -> dict:
        return await service.set_consent(self._session, customer_id, granted, now)

    async def create(self, customer_id: uuid.UUID, req: MemoryCreate, now: datetime) -> tuple[MemoryItemOut, bool]:
        item, replayed = await service.create(self._session, customer_id, req, now)
        return MemoryItemOut.model_validate(item), replayed

    async def list_items(self, customer_id: uuid.UUID, now: datetime) -> list[MemoryItemOut]:
        return [MemoryItemOut.model_validate(item) for item in await service.list_items(self._session, customer_id, now)]

    async def get_item(self, customer_id: uuid.UUID, item_id: uuid.UUID, now: datetime) -> MemoryItemOut:
        return MemoryItemOut.model_validate(await service.get_item(self._session, customer_id, item_id, now))

    async def update(self, customer_id: uuid.UUID, item_id: uuid.UUID, req: MemoryUpdate, now: datetime) -> MemoryItemOut:
        return MemoryItemOut.model_validate(await service.update(self._session, customer_id, item_id, req, now))

    async def delete(self, customer_id: uuid.UUID, item_id: uuid.UUID, now: datetime) -> bool:
        return await service.delete(self._session, customer_id, item_id, now)

    async def delete_all(self, customer_id: uuid.UUID, now: datetime) -> int:
        return await service.delete_all(self._session, customer_id, now)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


def get_memory_provider(session: AsyncSession = Depends(get_pg_session)) -> MemoryProvider:
    return PostgresMemoryProvider(session)
