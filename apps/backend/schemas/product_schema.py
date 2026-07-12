from enum import Enum
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import List, Optional
from datetime import datetime
from utils.bson import PyObjectId
from .variant_schema import VariantCreateSchema, VariantResponseSchema


class ProductCategory(str, Enum):
    SHAWLS = "shawls"
    STOLES = "stoles"


class ProductStatus(str, Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    OUT_OF_STOCK = "out_of_stock"
    ARCHIVED = "archived"


class ProductCreateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=160)
    slug: str = Field(..., min_length=1, max_length=180)

    cover_image_url: str = Field(..., min_length=1)
    images: List[str] = Field(default_factory=list, max_length=12)
    main_description: Optional[str] = Field(default=None, max_length=5000)
    category: ProductCategory = ProductCategory.SHAWLS
    price: Optional[int] = Field(default=None, ge=0)
    currency: str = Field(default="PKR", min_length=3, max_length=3)
    material: Optional[str] = Field(default=None, max_length=200)
    sizing: Optional[str] = Field(default=None, max_length=200)
    weight: Optional[str] = Field(default=None, max_length=100)
    item_number: Optional[str] = Field(default=None, max_length=100)
    status: ProductStatus = ProductStatus.ACTIVE

    variants: List[VariantCreateSchema] = Field(..., min_length=1, max_length=100)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        normalized = value.lower()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized):
            raise ValueError("slug must contain lowercase letters, numbers, and single hyphens only")
        return normalized

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def ensure_images_and_price(self):
        if not self.images:
            self.images = [self.cover_image_url]
        elif self.cover_image_url not in self.images:
            self.images.insert(0, self.cover_image_url)
        if self.price is None:
            self.price = min(variant.price for variant in self.variants)
        return self


class ProductResponseSchema(ProductCreateSchema):
    model_config = ConfigDict(populate_by_name=True)
    id: PyObjectId = Field(alias="_id")

    is_active: bool
    created_at: datetime
    updated_at: datetime

    variants: List[VariantResponseSchema]


class ProductListResponse(BaseModel):
    items: List[ProductResponseSchema]
    next_cursor: Optional[str] = None


class ProductStatusUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ProductStatus


class VariantStockUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant_id: PyObjectId
    stock: int = Field(..., ge=0)
