from pydantic import BaseModel, Field
from typing import Optional
from utils.bson import PyObjectId


class VariantCreateSchema(BaseModel):
    name: str = Field(..., min_length=1)
    image_url: str
    price: int = Field(..., ge=0)
    currency: str = "PKR"
    stock_status: str = "In stock"
    description: Optional[str] = None


class VariantResponseSchema(VariantCreateSchema):
    id: PyObjectId = Field(alias="_id")
    is_active: bool
