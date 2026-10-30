import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from database.pg import get_pg_session
from ingestion.fx import RateUnavailable, get_pkr_rate, suggest_pkr
from ingestion.normalize import InvalidSourceData, source_url_for_path
from ingestion.safe_fetch import SourcePolicy, UnsafeURL
from repositories import Conflict, InvalidDraft, InvalidTransition, NotFound, ProductUnavailable
from repositories import jobs
from repositories import staged as staged_repo
from schemas.ingestion_schema import (
    ApproveRequest, JobCreateRequest, JobListResponse, JobResponse, PkrSuggestion, RejectRequest,
    SourceInfo, StagedProductListResponse, StagedProductResponse, StagedStatus,
)
from schemas.product_schema import ProductCreateSchema, ProductStatus
from security.admin_auth import require_admin_api_key
from utils.pagination import decode_cursor, encode_cursor

router = APIRouter(
    prefix="/products/admin/ingestion",
    tags=["Ingestion"],
    dependencies=[Depends(require_admin_api_key)],
)
S = StagedStatus
CATALOGUE_FIELDS = ("name", "slug", "cover_image_url", "images", "main_description", "category", "material", "sizing", "weight")


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


def _review_error(exc: Exception, action: str) -> HTTPException:
    """Repository errors -> the status codes and wording the review API has always used."""
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail="Staged product not found")
    if isinstance(exc, InvalidTransition):
        return HTTPException(status_code=409, detail=f"Cannot {action} a staged product that is {exc.current}")
    if isinstance(exc, ProductUnavailable):
        return HTTPException(status_code=409, detail="Catalogue product is missing or archived")
    if isinstance(exc, Conflict):
        detail = "A product with this slug already exists" if exc.code == Conflict.SLUG_EXISTS else str(exc)
        return HTTPException(status_code=409, detail=detail)
    return HTTPException(status_code=422, detail="Staged product is not valid for the catalogue")


# ---- source & jobs --------------------------------------------------------

@router.get("/source", response_model=SourceInfo)
async def get_source():
    return SourceInfo(
        source_id=settings.ingestion_source_id, name=settings.ingestion_source_name,
        domain=settings.ingestion_source_domain, authorized=settings.ingestion_source_authorized,
    )


@router.post("/jobs", response_model=JobResponse, status_code=201)
async def create_job(payload: JobCreateRequest, response: Response, session: AsyncSession = Depends(get_pg_session)):
    policy = SourcePolicy.from_settings()
    try:
        source_url_for_path(payload.path, policy)
    except (InvalidSourceData, UnsafeURL) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    async with session.begin():
        job, created = await jobs.create_job(session, source_id=settings.ingestion_source_id, path=payload.path)
    if not created:
        # Same source+path already has a job; return it rather than queueing a duplicate.
        response.status_code = 200
    return job


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(limit: int = Query(default=20, ge=1, le=100), session: AsyncSession = Depends(get_pg_session)):
    return {"items": await jobs.list_jobs(session, limit)}


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, session: AsyncSession = Depends(get_pg_session)):
    job = await jobs.get_job(session, _uuid(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: str, session: AsyncSession = Depends(get_pg_session)):
    async with session.begin():
        job = await jobs.cancel_job(session, _uuid(job_id))
    if not job:
        raise HTTPException(status_code=409, detail="Job is not queued, retrying or running")
    return job


@router.post("/jobs/{job_id}/rerun", response_model=JobResponse)
async def rerun_job(job_id: str, session: AsyncSession = Depends(get_pg_session)):
    async with session.begin():
        job = await jobs.requeue_job(session, _uuid(job_id))
    if not job:
        raise HTTPException(status_code=409, detail="Only finished jobs can be rerun")
    return job


# ---- staged products ------------------------------------------------------

@router.get("/staged", response_model=StagedProductListResponse)
async def list_staged(
    status: StagedStatus | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    session: AsyncSession = Depends(get_pg_session),
):
    page = await staged_repo.list_staged(session, status=status.value if status else None, limit=limit, after=_after(cursor))
    return {"items": page.items, "next_cursor": encode_cursor(*page.next_after) if page.next_after else None}


@router.get("/staged/{staged_id}", response_model=StagedProductResponse)
async def get_staged(staged_id: str, session: AsyncSession = Depends(get_pg_session)):
    row = await staged_repo.get_staged(session, _uuid(staged_id))
    if not row:
        raise HTTPException(status_code=404, detail="Staged product not found")
    return row


@router.get("/staged/{staged_id}/pkr-suggestion", response_model=PkrSuggestion)
async def pkr_suggestion(staged_id: str, session: AsyncSession = Depends(get_pg_session)):
    """Reference PKR value of the source price. Read-only: nothing is saved and no price is set."""
    row = await staged_repo.get_staged(session, _uuid(staged_id))
    if not row:
        raise HTTPException(status_code=404, detail="Staged product not found")
    price, currency = row.source_price, row.source_currency
    if price is None or not currency:
        raise HTTPException(status_code=409, detail="The source price or currency is unknown; set the PKR price manually")
    try:
        rate = await get_pkr_rate(currency)
    except RateUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PkrSuggestion(
        source_price=float(price), source_currency=currency.upper(), rate=rate.rate, rate_date=rate.date,
        suggested_pkr=suggest_pkr(float(price), rate),
        note="Reference conversion only. It excludes margin, shipping, duty and tax; the reviewer sets the retail price.",
    )


def _check_catalogue_ready(draft: dict, price: int, stock: int) -> None:
    """The same validation the catalogue applies to a created product, so a bad draft is a 422 not a 500."""
    try:
        ProductCreateSchema.model_validate({
            **{k: draft[k] for k in CATALOGUE_FIELDS},
            "price": price,
            "currency": "PKR",
            "status": ProductStatus.DRAFT.value,
            "variants": [{**v, "price": price, "stock": stock} for v in draft["variants"]],
        })
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Staged product is not valid for the catalogue") from exc


@router.post("/staged/{staged_id}/approve", response_model=StagedProductResponse)
async def approve(staged_id: str, payload: ApproveRequest, session: AsyncSession = Depends(get_pg_session)):
    """Creates the catalogue product as an inactive draft in ONE transaction; publishing is a separate action."""
    oid = _uuid(staged_id)
    try:
        async with session.begin():
            current = await staged_repo.get_staged(session, oid)
            if current is not None and current.status == S.PENDING_REVIEW.value:
                _check_catalogue_ready(current.product, payload.price, payload.stock)
            return await staged_repo.approve(session, oid, price=payload.price, stock=payload.stock)
    except (NotFound, InvalidTransition, Conflict, InvalidDraft) as exc:
        raise _review_error(exc, "approve") from exc


@router.post("/staged/{staged_id}/reject", response_model=StagedProductResponse)
async def reject(staged_id: str, payload: RejectRequest, session: AsyncSession = Depends(get_pg_session)):
    try:
        async with session.begin():
            return await staged_repo.reject(session, _uuid(staged_id), payload.reason)
    except (NotFound, InvalidTransition, InvalidDraft) as exc:
        raise _review_error(exc, "reject") from exc


@router.post("/staged/{staged_id}/publish", response_model=StagedProductResponse)
async def publish(staged_id: str, session: AsyncSession = Depends(get_pg_session)):
    """Explicit, human-triggered: the only route that makes an ingested product public."""
    try:
        async with session.begin():
            return await staged_repo.publish(session, _uuid(staged_id), actor="admin")
    except (NotFound, InvalidTransition, ProductUnavailable, Conflict) as exc:
        raise _review_error(exc, "publish") from exc


@router.post("/staged/{staged_id}/unpublish", response_model=StagedProductResponse)
async def unpublish(staged_id: str, session: AsyncSession = Depends(get_pg_session)):
    try:
        async with session.begin():
            return await staged_repo.unpublish(session, _uuid(staged_id))
    except (NotFound, InvalidTransition) as exc:
        raise _review_error(exc, "unpublish") from exc


@router.post("/staged/{staged_id}/archive", response_model=StagedProductResponse)
async def archive(staged_id: str, session: AsyncSession = Depends(get_pg_session)):
    try:
        async with session.begin():
            return await staged_repo.archive(session, _uuid(staged_id))
    except (NotFound, InvalidTransition) as exc:
        raise _review_error(exc, "archive") from exc
