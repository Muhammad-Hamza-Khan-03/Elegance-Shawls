from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from database.db import get_db
from models.product_model import build_product_document
from schemas.product_schema import (
    ProductCreateSchema,
    ProductListResponse,
    ProductResponseSchema,
    ProductStatus,
    ProductStatusUpdateSchema,
    VariantStockUpdateSchema,
)
from security.admin_auth import require_admin_api_key
from utils.pagination import decode_cursor, encode_cursor


router = APIRouter(prefix="/products", tags=["Products"])
admin_router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(require_admin_api_key)],
)


def _object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail="Invalid identifier")
    return ObjectId(value)


def _active_query() -> dict:
    return {"is_active": True, "status": ProductStatus.ACTIVE.value}


def _cursor_query(cursor: str | None, base: dict) -> dict:
    query = dict(base)
    if not cursor:
        return query
    try:
        data = decode_cursor(cursor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc
    query["$or"] = [
        {"created_at": {"$lt": data["created_at"]}},
        {"created_at": data["created_at"], "_id": {"$lt": data["_id"]}},
    ]
    return query


async def _page(db, query: dict, limit: int) -> ProductListResponse:
    cursor = db.products.find(query).sort([("created_at", -1), ("_id", -1)]).limit(limit + 1)
    products = await cursor.to_list(length=limit + 1)
    next_cursor = None
    if len(products) > limit:
        products.pop()
        last = products[-1]
        next_cursor = encode_cursor(last["created_at"], last["_id"])
    return ProductListResponse(items=products, next_cursor=next_cursor)


@router.get("/", response_model=ProductListResponse)
async def get_products(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await _page(db, _cursor_query(cursor, _active_query()), limit)


@router.get("/slug/{slug}", response_model=ProductResponseSchema)
async def get_product_by_slug(slug: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    product = await db.products.find_one({"slug": slug.lower(), **_active_query()})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@admin_router.post("/", response_model=ProductResponseSchema, status_code=201)
async def create_product(payload: ProductCreateSchema, db: AsyncIOMotorDatabase = Depends(get_db)):
    if await db.products.find_one({"slug": payload.slug}, {"_id": 1}):
        raise HTTPException(status_code=409, detail="Product slug already exists")
    document = build_product_document(payload.model_dump(mode="json"))
    try:
        await db.products.insert_one(document)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="Product slug already exists") from exc
    return document


@admin_router.get("/", response_model=ProductListResponse)
async def get_all_products(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await _page(db, _cursor_query(cursor, {}), limit)


@admin_router.get("/{product_id}", response_model=ProductResponseSchema)
async def get_product(product_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    product = await db.products.find_one({"_id": _object_id(product_id)})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@admin_router.put("/{product_id}", response_model=ProductResponseSchema)
async def update_product(
    product_id: str,
    payload: ProductCreateSchema,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    replacement = build_product_document(payload.model_dump(mode="json"))
    replacement.pop("_id")
    replacement.pop("created_at")
    replacement["updated_at"] = datetime.now(timezone.utc)
    try:
        product = await db.products.find_one_and_update(
            {"_id": _object_id(product_id)},
            {"$set": replacement},
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="Product slug already exists") from exc
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@admin_router.patch("/{product_id}/status", response_model=ProductResponseSchema)
async def update_product_status(
    product_id: str,
    payload: ProductStatusUpdateSchema,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    product = await db.products.find_one_and_update(
        {"_id": _object_id(product_id)},
        {"$set": {
            "status": payload.status.value,
            "is_active": payload.status is ProductStatus.ACTIVE,
            "updated_at": datetime.now(timezone.utc),
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@admin_router.patch("/{product_id}/stock", response_model=ProductResponseSchema)
async def update_variant_stock(
    product_id: str,
    payload: VariantStockUpdateSchema,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    stock_status = "In stock" if payload.stock > 0 else "Out of stock"
    product = await db.products.find_one_and_update(
        {"_id": _object_id(product_id), "variants._id": payload.variant_id},
        {"$set": {
            "variants.$.stock": payload.stock,
            "variants.$.stock_status": stock_status,
            "updated_at": datetime.now(timezone.utc),
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product or variant not found")
    return product


@admin_router.delete("/{product_id}", response_model=ProductResponseSchema)
async def archive_product(product_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    product = await db.products.find_one_and_update(
        {"_id": _object_id(product_id)},
        {"$set": {
            "status": ProductStatus.ARCHIVED.value,
            "is_active": False,
            "updated_at": datetime.now(timezone.utc),
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


router.include_router(admin_router)
