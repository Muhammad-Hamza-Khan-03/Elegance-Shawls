from datetime import datetime, timezone
from collections.abc import Iterable

from bson import ObjectId


def _variant_ids(variants: list[dict], existing_ids: Iterable[ObjectId]) -> list[ObjectId]:
    """Keep a submitted id only if it already belongs to this product, once."""
    available = {str(value) for value in existing_ids}
    ids = []
    for variant in variants:
        submitted = variant.get("id")
        if submitted and submitted in available:
            available.discard(submitted)
            ids.append(ObjectId(submitted))
        else:
            ids.append(ObjectId())
    return ids


def build_product_document(payload: dict, existing_variant_ids: Iterable[ObjectId] = ()) -> dict:
    now = datetime.now(timezone.utc)
    variant_ids = _variant_ids(payload["variants"], existing_variant_ids)

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
                "_id": variant_id,
                "name": v["name"],
                "color": v.get("color"),
                "size": v["size"],
                "image_url": v["image_url"],
                "price": v["price"],
                "currency": v.get("currency", "PKR"),
                # Derived like the stock endpoint so status never contradicts the count.
                "stock_status": "In stock" if v["stock"] > 0 else "Out of stock",
                "stock": v["stock"],
                "description": v.get("description"),
                "is_active": True,
            }
            for v, variant_id in zip(payload["variants"], variant_ids)
        ],

        "is_active": payload["status"] == "active",
        "created_at": now,
        "updated_at": now,
    }
