"""POST /v1/search: read-only catalogue search with deterministic hard constraints (no model, no writes)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from catalog import search as catalogue
from catalog.query import parse_query
from database.pg import get_pg_session
from repositories import products as repo
from schemas.product_schema import ProductResponseSchema
from utils.pagination import decode_cursor, encode_cursor

router = APIRouter(prefix="/v1/search", tags=["Search"])


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str = Field(default="", max_length=200)
    limit: int = Field(default=20, ge=1, le=catalogue.MAX_LIMIT)
    cursor: str | None = Field(default=None, max_length=512)   # the next_cursor of the previous page


class SearchHit(BaseModel):
    product: ProductResponseSchema
    matched_variant_ids: list[uuid.UUID]   # the active variants that satisfy every constraint


class SearchResponse(BaseModel):
    """Results are newest first. A page may hold fewer than `limit` items while `next_cursor` is set (the
    per-request scan budget ran out): keep requesting with it until it is null. Nothing is dropped."""

    items: list[SearchHit]
    next_cursor: str | None = None
    filters: dict                          # the hard constraints that were applied
    text: list[str]                        # unrecognised words, all of which must appear in the product
    unsupported: list[str]                 # non-empty means the query was only partly understood: no results


@router.post("", response_model=SearchResponse)
@router.post("/", response_model=SearchResponse, include_in_schema=False)
async def search_catalogue(body: SearchRequest, session: AsyncSession = Depends(get_pg_session)):
    try:
        after = decode_cursor(body.cursor) if body.cursor else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc
    parsed = parse_query(body.q)

    async def fetch(position, n):
        return await repo.search_batch(session, parsed, position, n)

    hits, position = await catalogue.search_page(fetch, parsed, limit=body.limit, after=after)
    return SearchResponse(
        items=[SearchHit(product=ProductResponseSchema.model_validate(h.product),
                         matched_variant_ids=list(h.variant_ids)) for h in hits],
        next_cursor=encode_cursor(*position) if position else None,
        filters=parsed.filters(), text=list(parsed.text), unsupported=list(parsed.unsupported),
    )
