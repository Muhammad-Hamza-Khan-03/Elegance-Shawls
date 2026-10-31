import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict


class EnrichmentResponse(BaseModel):
    """A reviewable suggestion. It is never catalogue truth: `authoritative` is always false and nothing applies it."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    staged_product_id: uuid.UUID
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    authoritative: Literal[False] = False
    suggestions: Optional[dict[str, Any]] = None
    validation_errors: list[str]
    provider: str
    model: str
    prompt_version: str
    vocabulary_version: str
    input_content_hash: str
    attempts: int
    last_error: Optional[str] = None
    trace_id: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
