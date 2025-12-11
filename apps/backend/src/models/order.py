from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey, Integer,DECIMAL, Enum, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from ..core.database import Base
import enum

class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Nullable for guest checkout
    total_amount = Column(DECIMAL(10, 2), nullable=False)
    status = Column(Enum(OrderStatus, values_callable=lambda obj: [e.value for e in obj]), default=OrderStatus.PENDING, nullable=False)
    location = Column(String(255), nullable=False)
    address = Column(Text, nullable=False)
    email = Column(String(255), nullable=False)
    whatsapp = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="orders")
    order_items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(DECIMAL(10, 2), nullable=False)  # Price at purchase time
    
    # Relationships
    order = relationship("Order", back_populates="order_items")
    product_variant = relationship("ProductVariant", back_populates="order_items")
