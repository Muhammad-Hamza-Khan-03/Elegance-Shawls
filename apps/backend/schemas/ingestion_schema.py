import uuid
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .product_schema import ProductCategory


class StagedStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    ARCHIVED = "archived"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    RETRYING = "retrying"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Anything not listed is an invalid transition.
STAGED_TRANSITIONS: dict[StagedStatus, set[StagedStatus]] = {
    StagedStatus.PENDING_REVIEW: {StagedStatus.APPROVED, StagedStatus.REJECTED},
    StagedStatus.APPROVED: {StagedStatus.PUBLISHED, StagedStatus.ARCHIVED},
    StagedStatus.PUBLISHED: {StagedStatus.UNPUBLISHED, StagedStatus.ARCHIVED},
    StagedStatus.UNPUBLISHED: {StagedStatus.PUBLISHED, StagedStatus.ARCHIVED},
    StagedStatus.REJECTED: {StagedStatus.ARCHIVED},
    StagedStatus.ARCHIVED: set(),
}

JOB_TERMINAL = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}


def can_transition(current: StagedStatus, target: StagedStatus) -> bool:
    return target in STAGED_TRANSITIONS[current]


class StagedVariant(BaseModel):
    name: str
    color: Optional[str] = None
    size: str = "Free Size"
    image_url: str
    stock: int = 0


class StagedProductDraft(BaseModel):
    """Normalized Elegance-shaped fields. Price is deliberately absent: a human sets PKR."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=160)
    slug: str = Field(..., min_length=1, max_length=180)
    cover_image_url: str
    images: List[str] = Field(default_factory=list, max_length=12)
    main_description: Optional[str] = Field(default=None, max_length=5000)
    category: ProductCategory = ProductCategory.SHAWLS
    material: Optional[str] = Field(default=None, max_length=200)
    sizing: Optional[str] = Field(default=None, max_length=200)
    weight: Optional[str] = Field(default=None, max_length=100)
    variants: List[StagedVariant] = Field(..., min_length=1, max_length=100)


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    at: datetime
    action: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    actor: str = "admin"
    note: Optional[str] = None


class StagedProductResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: uuid.UUID = Field(alias="_id")
    source_id: str
    source_name: str
    source_url: str
    source_product_id: Optional[str] = None
    source_content_hash: str
    fetched_at: datetime
    normalized_at: datetime
    ingestion_job_id: Optional[uuid.UUID] = None
    source_price: Optional[float] = None
    source_currency: Optional[str] = None
    status: StagedStatus
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    product: dict[str, Any]
    source_attributes: dict[str, Any] = Field(default_factory=dict)
    missing_fields: List[str] = Field(default_factory=list)
    stock_known: bool = False
    latest_source_hash: Optional[str] = None
    product_id: Optional[uuid.UUID] = None
    audit: List[AuditEntry] = Field(default_factory=list)


class StagedProductListResponse(BaseModel):
    items: List[StagedProductResponse]
    next_cursor: Optional[str] = None


class ApproveRequest(BaseModel):
    """The reviewer supplies what the source cannot: the PKR retail price and stock."""
    model_config = ConfigDict(extra="forbid")

    price: int = Field(..., ge=0)
    stock: int = Field(default=0, ge=0)


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(..., min_length=3, max_length=500)


class JobCreateRequest(BaseModel):
    """Only a path on the configured source. Full URLs from the browser are never accepted."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    path: str = Field(..., min_length=1, max_length=220)


class JobResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: uuid.UUID = Field(alias="_id")
    source_id: str
    path: str
    status: JobStatus
    attempts: int
    max_attempts: int
    available_at: datetime
    cancel_requested: bool = False
    last_error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class JobListResponse(BaseModel):
    items: List[JobResponse]


class SourceInfo(BaseModel):
    source_id: str
    name: str
    domain: str
    authorized: bool


class PkrSuggestion(BaseModel):
    """Reference conversion for the reviewer; never stored and never applied automatically."""
    source_price: float
    source_currency: str
    rate: float
    rate_date: str
    suggested_pkr: int
    note: str
