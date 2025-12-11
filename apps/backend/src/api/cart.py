from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.redis import get_redis
from ..core.security import get_current_user
from ..schemas import CartItem, CartUpsertRequest, CartQuantityUpdate, CartResponse
from ..services.cart_service import CartService
from ..services.variant_service import VariantService

router = APIRouter(prefix="/cart", tags=["Cart"])


def get_cart_service(redis=Depends(get_redis)) -> CartService:
    """Dependency that provides a CartService instance."""
    return CartService(redis)


@router.get("/", response_model=CartResponse)
def get_cart(
    current_user=Depends(get_current_user),
    cart_service: CartService = Depends(get_cart_service),
) -> CartResponse:
    """Get all cart items for the authenticated user."""
    items = cart_service.get_cart_items(current_user.id)
    return CartResponse(items=items)


@router.post("/", response_model=CartResponse, status_code=status.HTTP_200_OK)
def add_or_update_cart_item(
    payload: CartUpsertRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
    cart_service: CartService = Depends(get_cart_service),
) -> CartResponse:
    """
    Add an item to the cart or increment its quantity.
    Validates the variant exists before writing to Redis.
    """
    variant = VariantService.get_variant_by_id(db, payload.product_variant_id)
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")

    cart_service.add_item(current_user.id, payload.product_variant_id, payload.quantity)
    items = cart_service.get_cart_items(current_user.id)
    return CartResponse(items=items)


@router.put("/{variant_id}", response_model=CartResponse)
def update_cart_item_quantity(
    payload: CartQuantityUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
    cart_service: CartService = Depends(get_cart_service),
    variant_id: int = Path(..., gt=0),
) -> CartResponse:
    """Set the quantity for a cart item; removes the item if quantity <= 0."""
    variant = VariantService.get_variant_by_id(db, variant_id)
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")

    cart_service.update_quantity(current_user.id, variant_id, payload.quantity)
    items = cart_service.get_cart_items(current_user.id)
    return CartResponse(items=items)


@router.delete("/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cart_item(
    current_user=Depends(get_current_user),
    cart_service: CartService = Depends(get_cart_service),
    variant_id: int = Path(..., gt=0),
) -> None:
    """Remove an item from the cart."""
    cart_service.delete_item(current_user.id, variant_id)

