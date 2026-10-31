"""POST /v1/search: read-only catalogue search with deterministic hard constraints (no model, no writes)."""
import uuid
from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from catalog import search as catalogue
from catalog.query import parse_query
from configuration.config import settings
from database.pg import get_pg_session
from repositories import products as repo
from schemas.product_schema import ProductResponseSchema
from search import hybrid
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


class HybridSearchResponse(SearchResponse):
    """Same item shape as /v1/search; order is fused relevance and next_cursor is a different, opaque token."""

    semantic: bool   # false: no vector branch ran (disabled or unavailable) and the order is lexical-only


@router.post("/hybrid", response_model=HybridSearchResponse)
async def search_hybrid(body: SearchRequest, session: AsyncSession = Depends(get_pg_session)):
    """Exact filters first, then lexical + vector candidates fused by fixed RRF. Read-only; the embedding model and
    index are server configuration and cannot be chosen by the client."""
    parsed = parse_query(body.q)
    k_lex, k_sem, scan = settings.hybrid_lexical_k, settings.hybrid_semantic_k, settings.hybrid_max_scan
    provider, vector = await hybrid.query_vector(
        body.q, enabled=settings.embedding_enabled, name=settings.embedding_provider, dimensions=settings.embedding_dimensions)
    version, qhash = hybrid.search_version(provider, settings.embedding_index_version), hybrid.query_hash(body.q, parsed, k_lex, k_sem, scan)
    try:
        after = hybrid.decode_cursor(body.cursor, version=version, qhash=qhash) if body.cursor else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc

    async def fetch(position, n):
        return await repo.search_batch(session, replace(parsed, text=()), position, n)

    semantic = hybrid.semantic_from_database(session, provider, vector, settings.embedding_index_version) if provider else None
    hits, position = await hybrid.hybrid_page(fetch, parsed, semantic, limit=body.limit, after=after,
                                              k_lexical=k_lex, k_semantic=k_sem, max_scan=scan)
    return HybridSearchResponse(
        items=[SearchHit(product=ProductResponseSchema.model_validate(h.product),
                         matched_variant_ids=list(h.variant_ids)) for h in hits],
        next_cursor=hybrid.encode_cursor(position, version=version, qhash=qhash) if position else None,
        filters=parsed.filters(), text=list(parsed.text), unsupported=list(parsed.unsupported), semantic=provider is not None,
    )
