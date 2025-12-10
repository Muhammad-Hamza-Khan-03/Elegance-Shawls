from sqlalchemy.orm import Session
from ..models import ProductVariant
from ..schemas import ProductVariantCreate, ProductVariantUpdate
from typing import List, Optional, cast

class VariantService:
    @staticmethod
    def get_variants_by_product(db: Session, product_id: int) -> List[ProductVariant]:
        """Get all variants for a product"""
        return db.query(ProductVariant).filter(ProductVariant.product_id == product_id).all()
    
    @staticmethod
    def get_variant_by_id(db: Session, variant_id: int) -> Optional[ProductVariant]:
        """Get single variant by ID"""
        return db.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
    
    @staticmethod
    def create_variant(db: Session, variant: ProductVariantCreate) -> ProductVariant:
        """Create a new product variant"""
        db_variant = ProductVariant(
            product_id=variant.product_id,
            color=variant.color,
            size=variant.size,
            price=variant.price,
            stock=variant.stock,
            image_url=variant.image_url
        )
        db.add(db_variant)
        db.commit()
        db.refresh(db_variant)
        return db_variant
    
    @staticmethod
    def update_variant(db: Session, variant_id: int, variant: ProductVariantUpdate) -> Optional[ProductVariant]:
        """Update an existing variant"""
        db_variant = VariantService.get_variant_by_id(db, variant_id)
        if not db_variant:
            return None
        
        update_data = variant.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_variant, field, value)
        
        db.commit()
        db.refresh(db_variant)
        return db_variant
    
    @staticmethod
    def delete_variant(db: Session, variant_id: int) -> bool:
        """Delete a variant"""
        db_variant = VariantService.get_variant_by_id(db, variant_id)
        if not db_variant:
            return False
        
        db.delete(db_variant)
        db.commit()
        return True
    
    @staticmethod
    def update_variant_stock(db: Session, variant_id: int, quantity: int) -> Optional[ProductVariant]:
        """Update variant stock (for order processing)"""
        db_variant = VariantService.get_variant_by_id(db, variant_id)
        if not db_variant:
            return None
        
        # Cast to int to ensure we compare concrete Python values (avoids ColumnElement[bool] in condition)
        stock = cast(int, db_variant.stock)
        if stock < quantity:
            return None  # Not enough stock
        
        # assign via __dict__ to avoid static type checkers complaining about Column[int] vs int
        db_variant.__dict__['stock'] = stock - quantity
        db.commit()
        db.refresh(db_variant)
        return db_variant