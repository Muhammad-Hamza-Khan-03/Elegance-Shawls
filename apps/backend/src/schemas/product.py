from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from .productVariant import ProductVariantBase, ProductVariantResponse

class ProductBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    category: str = Field(..., pattern="^(shawl|stole)$")
    price: Decimal = Field(..., ge=0)
    stock: int = Field(default=0, ge=0)

class ProductCreate(ProductBase):
    variants: Optional[List[ProductVariantBase]] = []

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[Decimal] = None
    stock: Optional[int] = None

class ProductResponse(ProductBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    variants: List[ProductVariantResponse] = []
    
    model_config = ConfigDict(from_attributes=True)