from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SuggestionProductEvidence(BaseModel):
    product_id: UUID
    product_slug: str
    product_name: str
    product_revision: int
    variant_id: UUID | None
    matched_field: str
    matched_value: str


class SuggestionPolicy(BaseModel):
    consented: bool
    provider_allowed: bool
    provider_reason: str
    decision: str
    version: str


class SuggestionReasonOut(BaseModel):
    code: str
    text: str
    source_memory_ids: tuple[UUID, ...]
    source_provenance: tuple[str, ...]
    product_evidence: SuggestionProductEvidence
    policy: SuggestionPolicy
    generated_at: datetime
    engine_version: str


class SuggestionOut(BaseModel):
    id: UUID
    customer_id: UUID
    product_id: UUID
    reason: SuggestionReasonOut
    generated_at: datetime
    engine_version: str
    model_config = ConfigDict(from_attributes=True)


class SuggestionList(BaseModel):
    items: list[SuggestionOut]
    generated_at: datetime
    engine_version: str
