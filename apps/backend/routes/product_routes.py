import asyncio
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from database.pg import get_pg_session
from events.recorder import log_listing
from repositories import Conflict, InvalidDraft, NotFound
from repositories import products as repo
from repositories import search as hybrid
from repositories.embeddings import Target
from repositories.products import ProductInput, VariantFilter, VariantInput
from schemas.product_schema import (
    ProductCreateSchema,
    ProductListResponse,
    ProductResponseSchema,
    ProductStatusUpdateSchema,
    VariantStockUpdateSchema,
)
from security.admin_auth import require_admin
from semantic.embeddings import validate_vector
from semantic.fusion import FusionWeights
from semantic.representation import REPRESENTATION_VERSION
from utils.colour_vocabulary import normalize
from utils.pagination import decode_cursor, decode_offset_cursor, encode_cursor, encode_offset_cursor


log = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["Products"])
search_router = APIRouter(prefix="/v1/search", tags=["Search"])
admin_router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(require_admin)],
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


def get_query_embedder():
    """The query-embedding provider (object with `.config` and `.embed(text)`), or None for lexical-only search.
    No live provider exists yet (semantic.embeddings allowlists only the test-only fake), so production is lexical;
    tests override this dependency."""
    return None


def get_fusion_weights() -> FusionWeights:
    return FusionWeights()


async def _query_vector(embedder, q: str):
    try:
        return validate_vector(await asyncio.to_thread(embedder.embed, q.casefold()), embedder.config.dimensions)
    except Exception:  # provider, transport or vector trouble: degrade to lexical, never fail the search
        log.warning("query embedding unavailable; using lexical search", exc_info=True)
        return None


async def _hybrid_page(session, embedder, weights, q, cursor, limit, variant):
    """(page dict, True) when hybrid ranking served the request, else None to fall back to lexical."""
    vector = await _query_vector(embedder, q)
    if vector is None:
        return None
    cfg = embedder.config
    target = Target(cfg.provider, cfg.model, REPRESENTATION_VERSION)
    bound = hybrid.binding(q, variant, target, weights)
    try:
        offset = decode_offset_cursor(cursor, bound) if cursor else 0
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc
    ids, products = await hybrid.hybrid_ids(session, q=q, query_vector=vector, target=target, variant=variant, weights=weights)
    items, nxt = hybrid.page_of(ids, products, offset, limit)
    return {"items": items, "next_cursor": encode_offset_cursor(nxt, bound) if nxt else None}


async def _public_list(request, background, limit, cursor, q, session, variant=None, response=None, embedder=None, weights=None):
    q = (q or "").strip()[:100] or None
    result = None
    if q and embedder is not None:
        result = await _hybrid_page(session, embedder, weights or FusionWeights(), q, cursor, limit, variant)
    if result is None:
        page = await repo.list_products(session, public=True, limit=limit, after=_after(cursor), q=q, **({"variant": variant} if variant else {}))
        result = _page(page)
    elif response is not None:
        response.headers["X-Search-Mode"] = "hybrid"
    items = result["items"]
    # Best effort and after the response: an event failure never affects the catalogue.
    background.add_task(log_listing, request, limit=limit, paged=bool(cursor),
                        product_ids=[str(item.id) for item in items])
    return result


@router.get("/", response_model=ProductListResponse)
async def get_products(
    request: Request,
    background: BackgroundTasks,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    session: AsyncSession = Depends(get_pg_session),
):
    return await _public_list(request, background, limit, cursor, None, session)


@search_router.get("", response_model=ProductListResponse)
async def search_products(
    request: Request,
    background: BackgroundTasks,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    q: str | None = None,
    colour: str | None = None,
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    in_stock: bool = False,
    response: Response = None,
    session: AsyncSession = Depends(get_pg_session),
    embedder=Depends(get_query_embedder),
    weights: FusionWeights = Depends(get_fusion_weights),
):
    """Same live-published catalogue as GET /products/ plus `q`, under the M1 /v1/search contract path.
    colour/min_price/max_price/in_stock are ANDed on a single purchasable variant of each product.
    With `q` and a configured embedder the ranking is hybrid (X-Search-Mode: hybrid; cursors are offsets into a
    bounded ranked window); otherwise it is the lexical newest-first keyset search."""
    canonical = None
    if colour is not None:
        canonical = normalize(colour)
        if canonical is None:
            raise HTTPException(status_code=422, detail="Unknown colour")
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="min_price exceeds max_price")
    variant = VariantFilter(canonical, min_price, max_price, in_stock)
    has_filter = canonical or min_price is not None or max_price is not None or in_stock
    return await _public_list(request, background, limit, cursor, q, session, variant if has_filter else None, response, embedder, weights)


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
