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
        
        # Handle variants update if present
        variants_data = update_data.pop('variants', None)
        
        for field, value in update_data.items():
            if field == "category" and value:
                value = ProductCategory(value)
            setattr(db_product, field, value)
            
        if variants_data is not None:
            # Get existing variants mapped by ID
            existing_variants = {v.id: v for v in db_product.variants}
            
            # Keep track of variant IDs present in the update payload
            updated_variant_ids = set()
            
            for variant_payload in variants_data:
                variant_id = variant_payload.get('id')
                
                if variant_id and variant_id in existing_variants:
                    # Update existing variant
                    existing_variant = existing_variants[variant_id]
                    for key, value in variant_payload.items():
                        if key != 'id':
                            setattr(existing_variant, key, value)
                    updated_variant_ids.add(variant_id)
                else:
                    # Create new variant
                    new_variant_data = variant_payload.copy()
                    if 'id' in new_variant_data:
                        del new_variant_data['id']
                    
                    new_variant = ProductVariant(
                        product_id=db_product.id,
                        **new_variant_data
                    )
                    db.add(new_variant)
            
            # Delete variants not present in the payload
            for variant_id, variant in existing_variants.items():
                if variant_id not in updated_variant_ids:
                    db.delete(variant)
        
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