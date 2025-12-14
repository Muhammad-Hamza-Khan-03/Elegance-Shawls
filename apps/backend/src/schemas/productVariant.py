from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

class ProductVariantBase(BaseModel):
    color: str = Field(..., min_length=1, max_length=100)
    size: str = Field(..., min_length=1, max_length=50)
    price: Optional[Decimal] = None
    stock: int = Field(default=0, ge=0)
    image_url: Optional[str] = None

class ProductVariantCreate(ProductVariantBase):
    product_id: int

class ProductVariantUpsert(ProductVariantBase):
    id: Optional[int] = None

class ProductVariantUpdate(BaseModel):
    color: Optional[str] = None
    size: Optional[str] = None
    price: Optional[Decimal] = None
    stock: Optional[int] = None
    image_url: Optional[str] = None

class ProductVariantResponse(ProductVariantBase):
    id: int
    product_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)