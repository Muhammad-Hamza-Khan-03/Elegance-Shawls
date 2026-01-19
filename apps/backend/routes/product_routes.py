from fastapi import APIRouter, Depends, HTTPException, Query, status
from utils.pagination import decode_cursor, encode_cursor
from motor.motor_asyncio import AsyncIOMotorDatabase
from schemas.product_schema import ProductCreateSchema, ProductResponseSchema
from models.product_model import build_product_document
from database.db import get_db

router = APIRouter(prefix="/products", tags=["Products"])

# Admin route to create a new product
@router.post("/",
    response_model=ProductResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    payload: ProductCreateSchema,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    # Enforce slug uniqueness (production critical)
    existing = await db.products.find_one({"slug": payload.slug})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product with this slug already exists",
        )

    document = build_product_document(payload.model_dump())

    await db.products.insert_one(document)

    return document

@router.get("/slug/{slug}",
    response_model=ProductResponseSchema,
    status_code=status.HTTP_200_OK,
)
async def get_product_by_slug(slug: str,db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    Fetch a product by unique slug (SEO-safe)
    """
    product = await db.products.find_one(
        {
            "slug": slug,
            "is_active": True,
        }
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return product


# Public route to get active products
@router.get("/",
    response_model=list[ProductResponseSchema],
    status_code=status.HTTP_200_OK
)
async def get_products(
    limit:int=10,
    db: AsyncIOMotorDatabase = Depends(get_db)
):

    products_cursor = db.products.find({"is_active": True}).limit(limit).sort("created_at", -1)
    products = await products_cursor.to_list(length=limit)

    return products

# @router.get(
#     "/",
#     response_model=list[ProductResponseSchema],
#     status_code=status.HTTP_200_OK,
# )
# async def get_products(
#     limit: int = Query(20, ge=1, le=100),
#     cursor: str | None = None,
#     db: AsyncIOMotorDatabase = Depends(get_db),
# ):
#     """
#     Cursor-based pagination for products
#     """
    
#     query = {"is_active": True}

#     if cursor:
#         try:
#             cursor_data = decode_cursor(cursor)
#         except ValueError:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Invalid cursor",
#             )

#         query["$or"] = [
#             {"created_at": {"$lt": cursor_data["created_at"]}},
#             {
#                 "created_at": cursor_data["created_at"],
#                 "_id": {"$lt": cursor_data["_id"]},
#             },
#         ]

#     cursor_db = (
#         db.products()
#         .find(query)
#         .sort([("created_at", -1), ("_id", -1)])
#         .limit(limit + 1)
#     )

#     products = await cursor_db.to_list(length=limit + 1)

#     next_cursor = None
#     if len(products) > limit:
#         last = products.pop()
#         next_cursor = encode_cursor(last["created_at"], last["_id"])

#     return {
#         "items": products,
#         "next_cursor": next_cursor,
#     }


# Admin route to get all products including inactive ones
@router.get("/all/",
    response_model=list[ProductResponseSchema],
    status_code=status.HTTP_200_OK
)
async def get_all_products(
    limit:int=10,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    products_cursor = db.products.find().limit(limit).sort("created_at", -1)
    products = await products_cursor.to_list(length=limit)

    return products

