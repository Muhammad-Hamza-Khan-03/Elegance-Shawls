"""Admin-only enrichment suggestions for staged products. There is deliberately no apply/approve route:
suggestions are read-only artifacts and the existing staged review stays the only way to change a product."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from database.pg import get_pg_session
from enrichment.contract import VOCABULARY_VERSION
from enrichment.prompts import PROMPT_VERSION
from enrichment.service import NOT_REVIEWABLE, prepare
from llm.gateway import provider_of
from observability.tracing import current_ids
from repositories import enrichment as repo
from repositories import staged as staged_repo
from schemas.enrichment_schema import EnrichmentResponse
from security.admin_auth import require_admin_api_key
from workers.queues import QueueUnavailable, enqueue

router = APIRouter(
    prefix="/products/admin/ingestion/staged/{staged_id}/enrichment",
    tags=["Enrichment"],
    dependencies=[Depends(require_admin_api_key)],
)


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid identifier") from exc


@router.post("", response_model=EnrichmentResponse, status_code=202)
async def request_enrichment(staged_id: str, session: AsyncSession = Depends(get_pg_session)):
    """Queue one suggestion run, or return the existing result for the same input, prompt and model (idempotent)."""
    model = settings.enrichment_model
    if not model:
        raise HTTPException(status_code=503, detail="Enrichment is not configured")
    oid = _uuid(staged_id)
    async with session.begin():
        staged = await staged_repo.get_staged(session, oid)
        if staged is None:
            raise HTTPException(status_code=404, detail="Staged product not found")
        if staged.status in NOT_REVIEWABLE:
            raise HTTPException(status_code=409, detail=f"Cannot enrich a staged product that is {staged.status}")
        _, digest = prepare(staged.product)
        row, created = await repo.create(session, staged_id=oid, input_hash=digest, prompt_version=PROMPT_VERSION,
                                         model=model, vocabulary_version=VOCABULARY_VERSION, provider=provider_of(model),
                                         trace_id=current_ids()[0])
    if created:
        try:
            await enqueue("run_enrichment_job", str(row.id))
        except QueueUnavailable as exc:
            async with session.begin():
                await repo.finish(session, row.id, status="failed", last_error="queue_unavailable")
            raise HTTPException(status_code=503, detail="Job queue is unavailable") from exc
    return row


@router.get("", response_model=EnrichmentResponse)
async def get_enrichment(staged_id: str, session: AsyncSession = Depends(get_pg_session)):
    row = await repo.latest_for(session, _uuid(staged_id))
    if row is None:
        raise HTTPException(status_code=404, detail="No enrichment suggestion for this staged product")
    return row


@router.post("/{suggestion_id}/cancel", response_model=EnrichmentResponse)
async def cancel_enrichment(staged_id: str, suggestion_id: str, session: AsyncSession = Depends(get_pg_session)):
    async with session.begin():
        row = await repo.cancel(session, _uuid(staged_id), _uuid(suggestion_id))
    if row is None:
        raise HTTPException(status_code=409, detail="Suggestion not found or not queued or running")
    return row
