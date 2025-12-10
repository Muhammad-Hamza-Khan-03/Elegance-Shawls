from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Integer,Enum, DECIMAL, func
from sqlalchemy.orm import relationship
import enum
from ..core.database import Base

class ProductCategory(str, enum.Enum):
    SHAWL = "shawl"
    STOLE = "stole"

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(Enum(ProductCategory), nullable=False)
    price = Column(DECIMAL(10, 2), nullable=False)
    stock = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")

class ProductVariant(Base):
    __tablename__ = "product_variants"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    color = Column(String(100), nullable=False)
    size = Column(String(50), nullable=False)
    price = Column(DECIMAL(10, 2), nullable=True)  # Override product price if needed
    stock = Column(Integer, default=0, nullable=False)
    image_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    product = relationship("Product", back_populates="variants")
    order_items = relationship("OrderItem", back_populates="product_variant")