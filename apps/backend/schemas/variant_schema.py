from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
from utils.bson import PyObjectId


class VariantCreateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1)
    color: Optional[str] = Field(default=None, min_length=1)
    size: str = Field(default="Free Size", min_length=1)
    image_url: str = Field(..., min_length=1)
    price: int = Field(..., ge=0)
    currency: str = Field(default="PKR", min_length=3, max_length=3)
    stock: int = Field(default=0, ge=0)
    stock_status: str = "In stock"
    description: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class VariantResponseSchema(VariantCreateSchema):
    id: PyObjectId = Field(alias="_id")
    is_active: bool
