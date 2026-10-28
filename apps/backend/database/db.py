import asyncio

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional

from configuration.config import settings

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


async def connect_to_mongo() -> None:
    global _client, _db

    _client = AsyncIOMotorClient(
        settings.MONGODB_URI,
        maxPoolSize=20,
        minPoolSize=5,
        serverSelectionTimeoutMS=5000,
        uuidRepresentation="standard",
    )

    _db = _client[settings.MONGO_DB_NAME]
    await _client.admin.command("ping")
    await ensure_indexes(_db)


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.products.create_index("slug", unique=True, name="uq_products_slug")
    await db.products.create_index(
        [("is_active", 1), ("created_at", -1), ("_id", -1)],
        name="ix_products_public_feed",
    )
    await db.products.create_index("item_number", sparse=True, name="ix_products_item_number")


async def database_is_ready(timeout_seconds: float = 2.0) -> bool:
    if _client is None or _db is None:
        return False
    try:
        # Fail fast so probes see 503 rather than timing out while the driver waits for a server.
        await asyncio.wait_for(_client.admin.command("ping"), timeout_seconds)
        return True
    except Exception:
        return False


async def close_mongo_connection() -> None:
    global _client, _db
    if _client:
        _client.close()
    _client = None
    _db = None


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db
