"""Customer memory API shapes (M4-S1). Strict: unknown fields, wrong types and implicit coercion are all 422. Responses never
carry customer_id, fingerprint or idempotency_key."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from memory import policy

Category = Literal["preference", "session_constraint", "purchase_context"]
Source = Literal["user_explicit", "memory_page"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _text(value: str | None) -> str | None:
    return None if value is None else policy.clean_text(value)


class ConsentRequest(_Strict):
    granted: StrictBool


class ConsentResponse(BaseModel):
    granted: bool
    policy_version: str
    changed_at: datetime | None


class MemoryCreate(_Strict):
    idempotency_key: str = Field(pattern=policy.IDEMPOTENCY_PATTERN)
    category: Category
    key: str = Field(pattern=policy.KEY_PATTERN)
    value: str
    source: Source
    source_ref: str | None = Field(default=None, pattern=policy.SOURCE_REF_PATTERN)
    reason: str | None = None
    retention_days: StrictInt = Field(default=policy.DEFAULT_RETENTION_DAYS, ge=1, le=policy.MAX_RETENTION_DAYS)

    @field_validator("value", "reason")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return _text(v)


class MemoryUpdate(_Strict):
    """Key, category, source and retention are fixed at creation; to change them delete and create again."""
    value: str | None = None
    reason: str | None = None

    @field_validator("value", "reason")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return _text(v)

    @model_validator(mode="after")
    def _something_to_change(self):
        if not self.model_fields_set or (self.value is None and self.reason is None):
            raise ValueError("send value and/or reason")
        return self


class MemoryItemOut(BaseModel):
    id: uuid.UUID
    category: Category
    key: str
    value: str
    source: Source
    source_ref: str | None
    reason: str | None
    version: int
    retention_days: int
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MemoryList(BaseModel):
    items: list[MemoryItemOut]
    next_cursor: str | None = None   # the per-customer cap keeps the whole list in one page
