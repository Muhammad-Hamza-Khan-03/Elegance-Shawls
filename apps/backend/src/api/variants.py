from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, cast
from ..core.database import get_db
from ..core.security import get_current_admin
from ..schemas import ProductVariantCreate, ProductVariantUpdate, ProductVariantResponse
from ..services.variant_service import VariantService
from ..services.product_service import ProductService

router = APIRouter(prefix="/variants", tags=["Product Variants"])

@router.get("/product/{product_id}", response_model=List[ProductVariantResponse])
def get_product_variants(product_id: int, db: Session = Depends(get_db)):
    """Get all variants for a specific product"""
    # Verify product exists
    product = ProductService.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    variants = VariantService.get_variants_by_product(db, product_id)
    return variants

@router.get("/{variant_id}", response_model=ProductVariantResponse)
def get_variant(variant_id: int, db: Session = Depends(get_db)):
    """Get single variant by ID"""
    variant = VariantService.get_variant_by_id(db, variant_id)
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found"
        )
    return variant

@router.post("/", response_model=ProductVariantResponse, status_code=status.HTTP_201_CREATED)
def create_variant(
    variant: ProductVariantCreate,
    db: Session = Depends(get_db),
    current_admin = Depends(get_current_admin)
):
    """Create a new product variant (admin only)"""
    # Verify product exists
    product = ProductService.get_product_by_id(db, variant.product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    db_variant = VariantService.create_variant(db, variant)
    
    # Update product stock
    ProductService.update_product_stock(db, variant.product_id)
    
    return db_variant

@router.put("/{variant_id}", response_model=ProductVariantResponse)
def update_variant(
    variant_id: int,
    variant: ProductVariantUpdate,
    db: Session = Depends(get_db),
    current_admin = Depends(get_current_admin)
):
    """Update an existing variant (admin only)"""
    db_variant = VariantService.update_variant(db, variant_id, variant)
    if not db_variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found"
        )
    
    # Update product stock if variant stock changed
    if variant.stock is not None:
        ProductService.update_product_stock(db, cast(int, db_variant.product_id))
    
    return db_variant

@router.delete("/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variant(
    variant_id: int,
    db: Session = Depends(get_db),
    current_admin = Depends(get_current_admin)
):
    """Delete a variant (admin only)"""
    # Get variant to know product_id before deletion
    variant = VariantService.get_variant_by_id(db, variant_id)
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found"
        )
    
    product_id = cast(int,variant.product_id)
    success = VariantService.delete_variant(db, variant_id)
    
    if success:
        # Update product stock
        ProductService.update_product_stock(db, product_id)
    
    return None