from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from utils.bson import PyObjectId
from .variant_schema import VariantCreateSchema, VariantResponseSchema


class ProductCreateSchema(BaseModel):
    name: str = Field(..., min_length=1)
    slug: str = Field(..., min_length=1)

    cover_image_url: str
    main_description: Optional[str] = None

    variants: List[VariantCreateSchema]


class ProductResponseSchema(ProductCreateSchema):
    id: PyObjectId = Field(alias="_id")

    is_active: bool
    created_at: datetime
    updated_at: datetime

    variants: List[VariantResponseSchema]
