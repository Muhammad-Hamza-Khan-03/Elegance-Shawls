from sqlalchemy.orm import Session
from sqlalchemy import or_
from ..models import Product, ProductVariant, ProductCategory
from ..schemas import ProductCreate, ProductUpdate, ProductVariantBase
from typing import List, Optional

class ProductService:
    @staticmethod
    def get_products(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        category: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Product]:
        """Get all products with optional filters"""
        query = db.query(Product)
        
        if category:
            query = query.filter(Product.category == ProductCategory(category))
        
        if search:
            query = query.filter(
                or_(
                    Product.name.ilike(f"%{search}%"),
                    Product.description.ilike(f"%{search}%")
                )
            )
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_product_by_id(db: Session, product_id: int) -> Optional[Product]:
        """Get single product by ID"""
        return db.query(Product).filter(Product.id == product_id).first()
    
    @staticmethod
    def create_product(db: Session, product: ProductCreate) -> Product:
        """Create a new product with variants"""
        db_product = Product(
            name=product.name,
            description=product.description,
            category=ProductCategory(product.category),
            price=product.price,
            stock=product.stock
        )
        db.add(db_product)
        db.flush()  # Get the product ID
        
        # Create variants if provided
        if product.variants:
            for variant_data in product.variants:
                variant = ProductVariant(
                    product_id=db_product.id,
                    color=variant_data.color,
                    size=variant_data.size,
                    price=variant_data.price,
                    stock=variant_data.stock,
                    image_url=variant_data.image_url
                )
                db.add(variant)
        
        db.commit()
        db.refresh(db_product)
        return db_product
    
    @staticmethod
    def update_product(db: Session, product_id: int, product: ProductUpdate) -> Optional[Product]:
        """Update an existing product"""
        db_product = ProductService.get_product_by_id(db, product_id)
        if not db_product:
            return None
        
        update_data = product.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field == "category" and value:
                value = ProductCategory(value)
            setattr(db_product, field, value)
        
        db.commit()
        db.refresh(db_product)
        return db_product
    
    @staticmethod
    def delete_product(db: Session, product_id: int) -> bool:
        """Delete a product"""
        db_product = ProductService.get_product_by_id(db, product_id)
        if not db_product:
            return False
        
        db.delete(db_product)
        db.commit()
        return True
    
    @staticmethod
    def update_product_stock(db: Session, product_id: int) -> None:
        """Recalculate product stock from variants"""
        db_product = ProductService.get_product_by_id(db, product_id)
        if db_product:
            total_stock = sum(variant.stock for variant in db_product.variants)
            db_product.__dict__['stock'] = total_stock
            db.commit()