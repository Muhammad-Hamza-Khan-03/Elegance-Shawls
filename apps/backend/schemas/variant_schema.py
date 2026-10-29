import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VariantCreateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Identifies an existing variant on update; ignored on create and when unknown.
    id: Optional[uuid.UUID] = None
    name: str = Field(..., min_length=1)
    color: Optional[str] = Field(default=None, min_length=1)
    size: str = Field(default="Free Size", min_length=1)
    image_url: str = Field(..., min_length=1)
    price: int = Field(..., ge=0)
    currency: str = Field(default="PKR", min_length=3, max_length=3)
    stock: int = Field(default=0, ge=0)
    stock_status: str = "In stock"
    description: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def unknown_ids_are_ignored(cls, value):
        """A submitted id is only a hint to keep an existing variant; anything that is not a UUID (for
        example an identifier from before the PostgreSQL move) is unknown, so it is ignored, not an error."""
        try:
            return uuid.UUID(str(value)) if value is not None else None
        except ValueError:
            return None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class VariantResponseSchema(VariantCreateSchema):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID = Field(alias="_id")
    is_active: bool
