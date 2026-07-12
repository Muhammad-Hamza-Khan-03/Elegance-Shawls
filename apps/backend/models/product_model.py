from datetime import datetime, timezone
from bson import ObjectId


def build_product_document(payload: dict) -> dict:
    now = datetime.now(timezone.utc)

    return {
        "_id": ObjectId(),
        "name": payload["name"],
        "slug": payload["slug"],

        "cover_image_url": payload["cover_image_url"],
        "images": payload["images"],
        "main_description": payload.get("main_description"),
        "category": payload["category"],
        "price": payload["price"],
        "currency": payload["currency"],
        "material": payload.get("material"),
        "sizing": payload.get("sizing"),
        "weight": payload.get("weight"),
        "item_number": payload.get("item_number"),
        "status": payload["status"],

        "variants": [
            {
                "_id": ObjectId(),
                "name": v["name"],
                "color": v.get("color"),
                "size": v["size"],
                "image_url": v["image_url"],
                "price": v["price"],
                "currency": v.get("currency", "PKR"),
                "stock_status": v["stock_status"],
                "stock": v["stock"],
                "description": v.get("description"),
                "is_active": True,
            }
            for v in payload["variants"]
        ],

        "is_active": payload["status"] == "active",
        "created_at": now,
        "updated_at": now,
    }
