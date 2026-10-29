from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from configuration.config import settings
from database.db import get_db
from ingestion import jobs
from ingestion.fx import RateUnavailable, get_pkr_rate, suggest_pkr
from ingestion.normalize import InvalidSourceData, source_url_for_path
from ingestion.safe_fetch import SourcePolicy, UnsafeURL
from models.ingestion_model import audit_entry
from models.product_model import build_product_document
from routes.product_routes import _cursor_query, _object_id
from schemas.ingestion_schema import (
    STAGED_TRANSITIONS, ApproveRequest, JobCreateRequest, JobListResponse, JobResponse, PkrSuggestion, RejectRequest,
    SourceInfo, StagedProductListResponse, StagedProductResponse, StagedStatus,
)
from schemas.product_schema import ProductCreateSchema, ProductStatus
from security.admin_auth import require_admin_api_key
from utils.pagination import encode_cursor

router = APIRouter(
    prefix="/products/admin/ingestion",
    tags=["Ingestion"],
    dependencies=[Depends(require_admin_api_key)],
)
S = StagedStatus


def _sources_from(status: StagedStatus) -> list[str]:
    return [src.value for src, targets in STAGED_TRANSITIONS.items() if status in targets]


async def _transition(db, staged_id: ObjectId, target: StagedStatus, action: str, *,
                      set_fields: dict | None = None, note: str | None = None) -> dict:
    """Atomically move a staged product to `target` if (and only if) the move is allowed."""
    ts = datetime.now(timezone.utc)
    current = await db.staged_products.find_one({"_id": staged_id}, {"status": 1})
    if not current:
        raise HTTPException(status_code=404, detail="Staged product not found")
    updated = await db.staged_products.find_one_and_update(
        {"_id": staged_id, "status": {"$in": _sources_from(target)}},
        {
            "$set": {"status": target.value, "updated_at": ts, **(set_fields or {})},
            "$push": {"audit": audit_entry(action, from_status=current["status"], to_status=target.value, note=note)},
        },
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot {action} a staged product that is {current['status']}",
        )
    return updated


async def _revert(db, staged_id: ObjectId, to_status: str, set_fields: dict | None = None) -> None:
    await db.staged_products.update_one(
        {"_id": staged_id},
        {"$set": {"status": to_status, "updated_at": datetime.now(timezone.utc), **(set_fields or {})},
         "$push": {"audit": audit_entry("rolled_back", to_status=to_status, actor="system")}},
    )


# ---- source & jobs --------------------------------------------------------

@router.get("/source", response_model=SourceInfo)
async def get_source():
    return SourceInfo(
        source_id=settings.ingestion_source_id, name=settings.ingestion_source_name,
        domain=settings.ingestion_source_domain, authorized=settings.ingestion_source_authorized,
    )


@router.post("/jobs", response_model=JobResponse, status_code=201)
async def create_job(payload: JobCreateRequest, response: Response, db: AsyncIOMotorDatabase = Depends(get_db)):
    policy = SourcePolicy.from_settings()
    try:
        source_url_for_path(payload.path, policy)
    except (InvalidSourceData, UnsafeURL) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    job, created = await jobs.create_job(db, source_id=settings.ingestion_source_id, path=payload.path)
    if not created:
        # Same source+path already has a job; return it rather than queueing a duplicate.
        response.status_code = 200
    return job


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(limit: int = Query(default=20, ge=1, le=100), db: AsyncIOMotorDatabase = Depends(get_db)):
    items = await db.ingestion_jobs.find({}).sort([("created_at", -1), ("_id", -1)]).to_list(length=limit)
    return JobListResponse(items=items)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    job = await db.ingestion_jobs.find_one({"_id": _object_id(job_id)})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    job = await jobs.cancel_job(db, _object_id(job_id))
    if not job:
        raise HTTPException(status_code=409, detail="Job is not queued, retrying or running")
    return job


@router.post("/jobs/{job_id}/rerun", response_model=JobResponse)
async def rerun_job(job_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    job = await jobs.requeue_job(db, _object_id(job_id))
    if not job:
        raise HTTPException(status_code=409, detail="Only finished jobs can be rerun")
    return job


# ---- staged products ------------------------------------------------------

@router.get("/staged", response_model=StagedProductListResponse)
async def list_staged(
    status: StagedStatus | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    base = {"status": status.value} if status else {}
    query = _cursor_query(cursor, base)
    rows = await db.staged_products.find(query).sort([("created_at", -1), ("_id", -1)]).limit(limit + 1).to_list(limit + 1)
    next_cursor = None
    if len(rows) > limit:
        rows.pop()
        next_cursor = encode_cursor(rows[-1]["created_at"], rows[-1]["_id"])
    return StagedProductListResponse(items=rows, next_cursor=next_cursor)


@router.get("/staged/{staged_id}", response_model=StagedProductResponse)
async def get_staged(staged_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    doc = await db.staged_products.find_one({"_id": _object_id(staged_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Staged product not found")
    return doc


@router.get("/staged/{staged_id}/pkr-suggestion", response_model=PkrSuggestion)
async def pkr_suggestion(staged_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Reference PKR value of the source price. Read-only: nothing is saved and no price is set."""
    doc = await db.staged_products.find_one({"_id": _object_id(staged_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Staged product not found")
    price, currency = doc.get("source_price"), doc.get("source_currency")
    if price is None or not currency:
        raise HTTPException(status_code=409, detail="The source price or currency is unknown; set the PKR price manually")
    try:
        rate = await get_pkr_rate(currency)
    except RateUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PkrSuggestion(
        source_price=price, source_currency=currency.upper(), rate=rate.rate, rate_date=rate.date,
        suggested_pkr=suggest_pkr(price, rate),
        note="Reference conversion only. It excludes margin, shipping, duty and tax; the reviewer sets the retail price.",
    )


@router.post("/staged/{staged_id}/approve", response_model=StagedProductResponse)
async def approve(staged_id: str, payload: ApproveRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Creates the catalogue product as an inactive draft; publishing is a separate action."""
    oid = _object_id(staged_id)
    product_id = ObjectId()
    staged = await _transition(
        db, oid, S.APPROVED, "approve",
        set_fields={"product_id": product_id, "stock_known": True,
                    "approved_price": payload.price, "approved_stock": payload.stock},
    )
    draft = staged["product"]
    try:
        body = ProductCreateSchema.model_validate({
            **{k: draft[k] for k in ("name", "slug", "cover_image_url", "images", "main_description",
                                     "category", "material", "sizing", "weight")},
            "price": payload.price,
            "currency": "PKR",
            "status": ProductStatus.DRAFT.value,
            "variants": [{**v, "price": payload.price, "stock": payload.stock} for v in draft["variants"]],
        })
    except ValueError as exc:
        await _revert(db, oid, S.PENDING_REVIEW.value, {"product_id": None, "stock_known": False})
        raise HTTPException(status_code=422, detail="Staged product is not valid for the catalogue") from exc

    document = build_product_document(body.model_dump(mode="json"))
    document["_id"] = product_id
    try:
        await db.products.insert_one(document)
    except DuplicateKeyError:
        await _revert(db, oid, S.PENDING_REVIEW.value, {"product_id": None, "stock_known": False})
        raise HTTPException(status_code=409, detail="A product with this slug already exists")
    await db.staged_products.update_one(
        {"_id": oid},
        {"$set": {"missing_fields": [f for f in staged["missing_fields"] if f not in ("price", "stock")]}},
    )
    return await db.staged_products.find_one({"_id": oid})


@router.post("/staged/{staged_id}/reject", response_model=StagedProductResponse)
async def reject(staged_id: str, payload: RejectRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    return await _transition(
        db, _object_id(staged_id), S.REJECTED, "reject",
        set_fields={"rejection_reason": payload.reason}, note=payload.reason,
    )


async def _set_product_state(db, product_id: ObjectId | None, status: ProductStatus) -> bool:
    if not product_id:
        return False
    result = await db.products.update_one(
        {"_id": product_id, "status": {"$ne": ProductStatus.ARCHIVED.value}},
        {"$set": {"status": status.value, "is_active": status is ProductStatus.ACTIVE,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    return result.matched_count == 1


@router.post("/staged/{staged_id}/publish", response_model=StagedProductResponse)
async def publish(staged_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    oid = _object_id(staged_id)
    previous = await db.staged_products.find_one({"_id": oid}, {"status": 1})
    staged = await _transition(db, oid, S.PUBLISHED, "publish")
    if not await _set_product_state(db, staged.get("product_id"), ProductStatus.ACTIVE):
        await _revert(db, oid, previous["status"])
        raise HTTPException(status_code=409, detail="Catalogue product is missing or archived")
    return staged


@router.post("/staged/{staged_id}/unpublish", response_model=StagedProductResponse)
async def unpublish(staged_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    oid = _object_id(staged_id)
    staged = await _transition(db, oid, S.UNPUBLISHED, "unpublish")
    await _set_product_state(db, staged.get("product_id"), ProductStatus.DRAFT)
    return staged


@router.post("/staged/{staged_id}/archive", response_model=StagedProductResponse)
async def archive(staged_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    oid = _object_id(staged_id)
    staged = await _transition(db, oid, S.ARCHIVED, "archive")
    await _set_product_state(db, staged.get("product_id"), ProductStatus.ARCHIVED)
    return staged
