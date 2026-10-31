"""Admin account, session and audit API shapes. Password hashes and token hashes are never part of any response."""
import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["viewer", "editor", "owner"]
Status = Literal["active", "disabled"]
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL.match(value) or not 3 <= len(value) <= 254:
        raise ValueError("Enter a valid email address")
    return value


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(_Strict):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=256)


class AccountCreateRequest(_Strict):
    email: str
    role: Role
    password: str = Field(max_length=256)
    display_name: str | None = Field(default=None, max_length=100)

    @field_validator("email")
    @classmethod
    def _normalise(cls, value: str) -> str:
        return _email(value)


class AccountUpdateRequest(_Strict):
    role: Role | None = None
    status: Status | None = None


class PasswordChangeRequest(_Strict):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(max_length=256)


class PasswordResetRequest(_Strict):
    new_password: str = Field(max_length=256)


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None
    role: Role
    status: Status
    last_login_at: datetime | None
    password_changed_at: datetime
    created_at: datetime


class AccountListResponse(BaseModel):
    items: list[AccountResponse]


class SessionResponse(BaseModel):
    """Returned only to the trusted Next.js server, which stores `token` in an HttpOnly cookie."""
    token: str
    expires_at: datetime
    account: AccountResponse


class WhoAmIResponse(BaseModel):
    account: AccountResponse | None   # None for the legacy shared key, which has no individual identity
    role: Role
    legacy: bool


class AuditEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    actor_type: str
    actor_id: str | None
    action: str
    target: str | None
    outcome: str
    detail: dict | None


class AuditListResponse(BaseModel):
    items: list[AuditEntryResponse]
