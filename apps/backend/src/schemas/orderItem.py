from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from .productVariant import ProductVariantResponse

class OrderItemBase(BaseModel):
    product_variant_id: int
    quantity: int = Field(..., ge=1)
    price: Decimal = Field(..., ge=0)

class OrderItemCreate(OrderItemBase):
    pass

class OrderItemResponse(OrderItemBase):
    id: int
    order_id: int
    product_variant: Optional[ProductVariantResponse] = None
    
    model_config = ConfigDict(from_attributes=True)
