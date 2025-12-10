from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from ..models import Order, OrderItem, OrderStatus
from ..schemas import OrderCreate, OrderUpdateStatus
from .variant_service import VariantService
from typing import List, Optional, cast
from decimal import Decimal

class OrderService:
    @staticmethod
    def get_orders(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        user_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> List[Order]:
        """Get all orders with optional filters"""
        query = db.query(Order)
        
        if user_id:
            query = query.filter(Order.user_id == user_id)
        
        if status:
            query = query.filter(Order.status == OrderStatus(status))
        
        return query.order_by(Order.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_order_by_id(db: Session, order_id: int) -> Optional[Order]:
        """Get single order by ID"""
        return db.query(Order).filter(Order.id == order_id).first()
    
    @staticmethod
    def create_order(db: Session, order: OrderCreate, user_id: Optional[int] = None) -> Optional[Order]:
        """Create a new order with items"""
        # Calculate total and validate stock
        total_amount = Decimal(0)
        order_items_data = []
        
        for item in order.items:
            variant = VariantService.get_variant_by_id(db, item.product_variant_id)
            if not variant:
                return None  # Variant not found
            
            if cast(int,variant.stock) < item.quantity:
                return None  # Insufficient stock
            
            # Use variant price or fall back to item price
            price = variant.price if cast(int,variant.price) else item.price
            total_amount += price * item.quantity
            
            order_items_data.append({
                "variant": variant,
                "quantity": item.quantity,
                "price": price
            })
        
        # Create order
        db_order = Order(
            user_id=user_id,
            total_amount=total_amount,
            location=order.location,
            address=order.address,
            email=order.email,
            whatsapp=order.whatsapp,
            status=OrderStatus.PENDING
        )
        db.add(db_order)
        db.flush()  # Get order ID
        
        # Create order items and update stock
        for item_data in order_items_data:
            order_item = OrderItem(
                order_id=db_order.id,
                product_variant_id=item_data["variant"].id,
                quantity=item_data["quantity"],
                price=item_data["price"]
            )
            db.add(order_item)
            
            # Reduce stock
            item_data["variant"].stock -= item_data["quantity"]
        
        db.commit()
        db.refresh(db_order)
        return db_order
    
    @staticmethod
    def update_order_status(db: Session, order_id: int, status_update: OrderUpdateStatus) -> Optional[Order]:
        """Update order status"""
        db_order = OrderService.get_order_by_id(db, order_id)
        if not db_order:
            return None
        
        db_order.__dict__['stock'] = OrderStatus(status_update.status)
        db.commit()
        db.refresh(db_order)
        return db_order
    
    @staticmethod
    def get_dashboard_stats(db: Session) -> dict:
        """Get dashboard statistics"""
        total_orders = db.query(func.count(Order.id)).scalar()
        total_revenue = db.query(func.sum(Order.total_amount)).scalar() or 0
        pending_orders = db.query(func.count(Order.id)).filter(Order.status == OrderStatus.PENDING).scalar()
        
        from ..models import Product
        total_products = db.query(func.count(Product.id)).scalar()
        low_stock_products = db.query(func.count(Product.id)).filter(Product.stock < 5).scalar()
        
        return {
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "pending_orders": pending_orders,
            "total_products": total_products,
            "low_stock_products": low_stock_products
        }
    
    @staticmethod
    def get_sales_report(db: Session, days: int = 30) -> List[dict]:
        """Get sales report for last N days"""
        from datetime import datetime, timedelta
        
        start_date = datetime.now() - timedelta(days=days)
        
        results = db.query(
            func.date(Order.created_at).label("date"),
            func.sum(Order.total_amount).label("total_sales"),
            func.count(Order.id).label("order_count")
        ).filter(
            Order.created_at >= start_date
        ).group_by(
            func.date(Order.created_at)
        ).order_by(
            func.date(Order.created_at)
        ).all()
        
        return [
            {
                "date": str(row.date),
                "total_sales": row.total_sales,
                "order_count": row.order_count
            }
            for row in results
        ]