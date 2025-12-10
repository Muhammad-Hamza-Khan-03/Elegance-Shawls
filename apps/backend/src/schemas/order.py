from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from .orderItem import OrderItemCreate, OrderItemResponse

class OrderBase(BaseModel):
    location: str = Field(..., min_length=2, max_length=255)
    address: str = Field(..., min_length=5)
    email: EmailStr
    whatsapp: str = Field(..., min_length=10, max_length=50)

class OrderCreate(OrderBase):
    items: List[OrderItemCreate] = Field(..., min_length=1)

class OrderUpdateStatus(BaseModel):
    status: str = Field(..., pattern="^(pending|confirmed|shipped|delivered)$")

class OrderResponse(OrderBase):
    id: int
    user_id: Optional[int] = None
    total_amount: Decimal
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    order_items: List[OrderItemResponse] = []
    
    model_config = ConfigDict(from_attributes=True)