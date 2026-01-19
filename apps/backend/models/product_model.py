from datetime import datetime
from bson import ObjectId


def build_product_document(payload: dict) -> dict:
    now = datetime.utcnow()

    return {
        "_id": ObjectId(),
        "name": payload["name"],
        "slug": payload["slug"],

        "cover_image_url": payload["cover_image_url"],
        "main_description": payload.get("main_description"),

        "variants": [
            {
                "_id": ObjectId(),
                "name": v["name"],
                "image_url": v["image_url"],
                "price": v["price"],
                "currency": v.get("currency", "PKR"),
                "stock_status": v["stock_status"],
                "description": v.get("description"),
                "is_active": True,
            }
            for v in payload["variants"]
        ],

        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
