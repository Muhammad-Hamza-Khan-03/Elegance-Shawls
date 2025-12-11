from pydantic import BaseModel, Field
from typing import List


class CartItem(BaseModel):
    """Simple representation of a cart line item."""

    product_variant_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)


class CartUpsertRequest(CartItem):
    """Payload for adding or incrementing a cart line item."""

    pass


class CartQuantityUpdate(BaseModel):
    """Payload for updating the quantity of an existing line item."""

    quantity: int = Field(..., gt=0)


class CartResponse(BaseModel):
    """Response model for cart operations."""

    items: List[CartItem]
