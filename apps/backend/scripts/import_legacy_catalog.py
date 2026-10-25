"""Preview a legacy catalog import; --apply inserts drafts into a separate database.

Uses MONGODB_URI from the process environment. Never accepts credentials as CLI
arguments, updates source records, overwrites target products, or publishes stock.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from bson import ObjectId, json_util
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.product_model import build_product_document
from schemas.product_schema import ProductCreateSchema


def prepare_product(source: dict) -> ProductCreateSchema:
    price = source.get("price")
    if not isinstance(price, dict):
        raise ValueError("legacy price must contain amount and currency")
    amount = price.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount != int(amount):
        raise ValueError("price requires review; refusing to round or invent a value")
    currency = price.get("currency")
    if not isinstance(currency, str) or len(currency) != 3:
        raise ValueError("currency requires review")
    category = source.get("category")
    label = category.get("name") if isinstance(category, dict) else category
    categories = {"shawl": "shawls", "shawls": "shawls", "stole": "stoles", "stoles": "stoles"}
    category = categories.get(str(label).strip().lower())
    if not category:
        raise ValueError("category requires review")
    images, variants, colors = [], [], set()
    for variation in source.get("variations", []):
        image = variation.get("image_url", "")
        if not isinstance(image, str) or not image.startswith("https://"):
            raise ValueError("image requires a valid HTTPS source")
        if image not in images:
            images.append(image)
        color = str(variation.get("color") or "").strip()
        if color.casefold() in colors:
            continue
        colors.add(color.casefold())
        variants.append({
            "name": color or "Unspecified color (review required)",
            "color": color or None,
            "size": str(source.get("sizing") or "Unspecified size (review required)"),
            "image_url": image, "price": int(amount), "currency": currency,
            "stock": 0, "stock_status": "Out of stock",
        })
    if not images:
        raise ValueError("product requires images")
    item = source.get("item_number")
    return ProductCreateSchema.model_validate({
        "name": source.get("name"), "slug": source.get("slug"),
        "cover_image_url": images[0], "images": images,
        "main_description": source.get("description"), "category": category,
        "price": int(amount), "currency": currency,
        "material": source.get("material"), "sizing": source.get("sizing"),
        "weight": source.get("weight"), "item_number": str(item) if item is not None else None,
        "status": "archived" if source.get("status") == "archived" else "draft",
        "variants": variants,
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", default="quill_ecommerce")
    parser.add_argument("--target-db", default="elegance_shawls")
    parser.add_argument("--input", type=Path, help="Optional local catalog snapshot for offline preview")
    parser.add_argument("--apply", action="store_true", help="Insert reviewed drafts; source is never modified")
    args = parser.parse_args()
    if args.source_db == args.target_db:
        parser.error("source and target must be different databases")
    client = None
    try:
        if args.input:
            products = json_util.loads(args.input.read_text())
        else:
            uri = os.environ.get("MONGODB_URI")
            if not uri:
                parser.error("MONGODB_URI must be set securely in the process environment")
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            products = list(client[args.source_db].products.find({}))
        prepared, invalid, slugs, issues = [], 0, set(), []
        for source in products:
            try:
                payload = prepare_product(source)
                if payload.slug in slugs:
                    raise ValueError("duplicate source slug")
                slugs.add(payload.slug)
                prepared.append((source, payload))
            except (ValueError, TypeError, OverflowError) as exc:
                invalid += 1
                issues.append({"slug": source.get("slug"), "reason": str(exc).splitlines()[0]})
        summary = {"source_count": len(products), "valid": len(prepared), "invalid": invalid,
                   "mode": "apply" if args.apply else "preview", "inserted": 0, "skipped_existing": 0,
                   "issues": issues,
                   "warnings": ["All imported inventory is zero stock.",
                                "Active legacy products become drafts; archived products remain archived.",
                                "Prices, currency, sizes, image rights and image compatibility need owner review."]}
        if invalid:
            print(json.dumps(summary))
            return 1
        if args.apply:
            if not client:
                uri = os.environ.get("MONGODB_URI")
                if not uri:
                    parser.error("MONGODB_URI is required for --apply")
                client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            target = client[args.target_db].products
            target.create_index("slug", unique=True, name="uq_products_slug")
            for source, payload in prepared:
                if target.find_one({"slug": payload.slug}, {"_id": 1}):
                    summary["skipped_existing"] += 1
                    continue
                document = build_product_document(payload.model_dump(mode="json"))
                source_id = source.get("_id")
                if isinstance(source_id, ObjectId):
                    document["_id"] = source_id
                target.insert_one(document)
                summary["inserted"] += 1
        print(json.dumps(summary))
        return 0
    except Exception as exc:
        # Driver exceptions can contain connection details; print only the class.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        return 1
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
