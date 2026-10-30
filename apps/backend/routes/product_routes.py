import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from database.pg import get_pg_session
from events.recorder import log_listing
from repositories import Conflict, InvalidDraft, NotFound
from repositories import products as repo
from repositories.products import ProductInput, VariantInput
from schemas.product_schema import (
    ProductCreateSchema,
    ProductListResponse,
    ProductResponseSchema,
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


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid identifier") from exc


def _after(cursor: str | None):
    if not cursor:
        return None
    try:
        return decode_cursor(cursor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc


def _to_input(payload: ProductCreateSchema) -> ProductInput:
    return ProductInput(
        slug=payload.slug, name=payload.name, cover_image_url=payload.cover_image_url, images=list(payload.images),
        main_description=payload.main_description, category=payload.category.value, price=payload.price,
        currency=payload.currency, material=payload.material, sizing=payload.sizing, weight=payload.weight,
        item_number=payload.item_number, status=payload.status.value,
        variants=[VariantInput(id=v.id, name=v.name, color=v.color, size=v.size, image_url=v.image_url,
                               price=v.price, currency=v.currency, stock=v.stock, description=v.description)
                  for v in payload.variants],
    )


def _page(page) -> dict:
    return {"items": page.items, "next_cursor": encode_cursor(*page.next_after) if page.next_after else None}


def _http(exc: Exception) -> HTTPException:
    """Repository errors keep the API's established status codes and wording."""
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, Conflict):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/", response_model=ProductListResponse)
async def get_products(
    request: Request,
    background: BackgroundTasks,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    session: AsyncSession = Depends(get_pg_session),
):
    page = await repo.list_products(session, public=True, limit=limit, after=_after(cursor))
    # Best effort and after the response: an event failure never affects the catalogue.
    background.add_task(log_listing, request, limit=limit, paged=bool(cursor),
                        product_ids=[str(item.id) for item in page.items])
    return _page(page)


@router.get("/slug/{slug}", response_model=ProductResponseSchema)
async def get_product_by_slug(slug: str, session: AsyncSession = Depends(get_pg_session)):
    product = await repo.get_public_product_by_slug(session, slug)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@admin_router.post("/", response_model=ProductResponseSchema, status_code=201)
async def create_product(payload: ProductCreateSchema, session: AsyncSession = Depends(get_pg_session)):
    try:
        async with session.begin():
            return await repo.create_product(session, _to_input(payload))
    except (Conflict, InvalidDraft) as exc:
        raise _http(exc) from exc


@admin_router.get("/", response_model=ProductListResponse)
async def get_all_products(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    session: AsyncSession = Depends(get_pg_session),
):
    return _page(await repo.list_products(session, public=False, limit=limit, after=_after(cursor)))


@admin_router.get("/{product_id}", response_model=ProductResponseSchema)
async def get_product(product_id: str, session: AsyncSession = Depends(get_pg_session)):
    product = await repo.get_product(session, _uuid(product_id))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@admin_router.put("/{product_id}", response_model=ProductResponseSchema)
async def update_product(
    product_id: str,
    payload: ProductCreateSchema,
    session: AsyncSession = Depends(get_pg_session),
):
    try:
        async with session.begin():
            return await repo.replace_product(session, _uuid(product_id), _to_input(payload))
    except (NotFound, Conflict, InvalidDraft) as exc:
        raise _http(exc) from exc


@admin_router.patch("/{product_id}/status", response_model=ProductResponseSchema)
async def update_product_status(
    product_id: str,
    payload: ProductStatusUpdateSchema,
    session: AsyncSession = Depends(get_pg_session),
):
    try:
        async with session.begin():
            return await repo.set_status(session, _uuid(product_id), payload.status.value)
    except (NotFound, Conflict) as exc:
        raise _http(exc) from exc


@admin_router.patch("/{product_id}/stock", response_model=ProductResponseSchema)
async def update_variant_stock(
    product_id: str,
    payload: VariantStockUpdateSchema,
    session: AsyncSession = Depends(get_pg_session),
):
    try:
        async with session.begin():
            return await repo.set_variant_stock(session, _uuid(product_id), payload.variant_id, payload.stock)
    except (NotFound, InvalidDraft) as exc:
        raise _http(exc) from exc


@admin_router.delete("/{product_id}", response_model=ProductResponseSchema)
async def archive_product(product_id: str, session: AsyncSession = Depends(get_pg_session)):
    try:
        async with session.begin():
            return await repo.archive_product(session, _uuid(product_id))
    except NotFound as exc:
        raise _http(exc) from exc


router.include_router(admin_router)
