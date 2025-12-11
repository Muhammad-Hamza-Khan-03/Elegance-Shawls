from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from ..core.database import get_db
from ..core.security import get_current_user, get_current_admin
from ..schemas import OrderCreate, OrderUpdateStatus, OrderResponse
from ..services.order_service import OrderService
from ..core.email import EmailService

router = APIRouter(prefix="/orders", tags=["Orders"])

@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    order: OrderCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)  # Optional: can allow guest checkout
):
    """Create a new order"""
    user_id = current_user.id if current_user else None
    
    db_order = OrderService.create_order(db, order, user_id)
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create order. Check product availability and stock."
        )
    
    # Use persisted order_items relationship; eager load will avoid extra queries if configured.
    EmailService.send_order_confirmation(
        to_email=order.email,
        customer_name=order.email.split("@")[0],
        order_id=db_order.id,
        total_amount=db_order.total_amount,
        order_items=[
            {
                "product_name": getattr(item.product_variant.product, "name", "Product"),
                "color": item.product_variant.color,
                "size": item.product_variant.size,
                "quantity": item.quantity,
                "price": float(item.price),
            }
            for item in db_order.order_items
        ],
    )

    EmailService.send_admin_notification(
        order_id=db_order.id,
        customer_name=order.email.split("@")[0],
        customer_email=order.email,
        customer_whatsapp=order.whatsapp,
        total_amount=db_order.total_amount,
        location=order.location
    )

    # TODO: Send WhatsApp notification
    return db_order

@router.post("/guest", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_guest_order(order: OrderCreate, db: Session = Depends(get_db)):
    """Create order without authentication (guest checkout)"""
    db_order = OrderService.create_order(db, order, user_id=None)
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create order. Check product availability and stock."
        )
    
    items = []
    for item in db_order.order_items:
        variant = item.product_variant
        items.append({
            "product_name": getattr(variant, "name", "Product"),  # fallback
            "color": variant.color,
            "size": variant.size,
            "quantity": item.quantity,
            "price": float(item.price)
        })

    EmailService.send_order_confirmation(
        to_email=db_order.email,
        customer_name=db_order.email.split("@")[0],  # You have no name field
        order_id=db_order.id,
        total_amount=float(db_order.total_amount),
        order_items=items
    )

    EmailService.send_admin_notification(
    order_id=db_order.id,
        customer_name=db_order.email.split("@")[0],
        customer_email=db_order.email,
        customer_whatsapp=db_order.whatsapp,
        total_amount=float(db_order.total_amount),
        location=db_order.location
    )

    return db_order

@router.get("/", response_model=List[OrderResponse])
def get_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(pending|confirmed|shipped|delivered)$"),
    db: Session = Depends(get_db),
    current_admin = Depends(get_current_admin)
):
    """Get all orders (admin only)"""
    orders = OrderService.get_orders(db, skip=skip, limit=limit, status=status)
    return orders

@router.get("/my-orders", response_model=List[OrderResponse])
def get_my_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get current user's orders"""
    orders = OrderService.get_orders(db, skip=skip, limit=limit, user_id=current_user.id)
    return orders

@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get single order by ID"""
    order = OrderService.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    # Check authorization: user can only see their own orders, admin can see all
    if current_user.role != "admin" and order.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this order"
        )
    
    return order

@router.put("/{order_id}/status", response_model=OrderResponse)
def update_order_status(
    order_id: int,
    status_update: OrderUpdateStatus,
    db: Session = Depends(get_db),
    current_admin = Depends(get_current_admin)
):
    """Update order status (admin only)"""
    db_order = OrderService.update_order_status(db, order_id, status_update)
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    EmailService.send_status_update(
        to_email=db_order.email,
        customer_name=db_order.email.split("@")[0],
        order_id=db_order.id,
        new_status=status_update.status
    )
    return db_order

@router.delete("/{order_id}", status_code=status.HTTP_200_OK)
def delete_order(
    order_id: int,
    db: Session = Depends(get_db),
    # current_admin = Depends(get_current_admin)
):
# TODO: Add Admin auth if necessary
    """Delete an order"""
    order_data = OrderService.delete_order(db, order_id)
    if not order_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    # Send email notification to admin
    EmailService.send_order_deletion_notification(
        order_id=order_data["id"],
        customer_name=order_data["email"].split("@")[0],
        customer_email=order_data["email"],
        customer_whatsapp=order_data["whatsapp"],
        total_amount=order_data["total_amount"],
        location=order_data["location"],
        order_status=order_data["status"],
        order_items=order_data["order_items"]
    )
    
    return {
        "message": "Order deleted successfully",
        "order_id": order_data["id"]
    }