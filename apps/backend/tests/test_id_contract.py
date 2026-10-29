"""Schemas treat identifiers as opaque UUID strings under the unchanged `_id` key, and ignore unknown variant hints."""
import uuid
from datetime import datetime, timezone

import pytest

from models.relational_model import Product, StagedProduct, StagedProductAudit, Variant
from schemas.ingestion_schema import StagedProductResponse
from schemas.product_schema import ProductCreateSchema, ProductResponseSchema, VariantStockUpdateSchema
from schemas.variant_schema import VariantCreateSchema

NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def variant_payload(**extra):
    return {"name": "V", "image_url": "https://x/v.jpg", "price": 10, **extra}


@pytest.mark.parametrize("hint", ["507f1f77bcf86cd799439011", "not-an-id", "", "123", 7])
def test_unknown_or_legacy_variant_ids_are_ignored_not_rejected(hint):
    assert VariantCreateSchema.model_validate(variant_payload(id=hint)).id is None


def test_a_real_uuid_variant_id_is_kept():
    value = uuid.uuid4()
    assert VariantCreateSchema.model_validate(variant_payload(id=str(value))).id == value
    assert VariantCreateSchema.model_validate(variant_payload()).id is None


def test_stock_update_requires_a_uuid_variant_id():
    assert VariantStockUpdateSchema.model_validate({"variant_id": str(uuid.uuid4()), "stock": 1})
    with pytest.raises(ValueError):
        VariantStockUpdateSchema.model_validate({"variant_id": "507f1f77bcf86cd799439011", "stock": 1})


def test_product_response_reads_orm_rows_and_serialises_uuids_as_strings_under_underscore_id():
    pid, vid = uuid.uuid4(), uuid.uuid4()
    product = Product(id=pid, slug="s", name="S", category="shawls", status="active", is_active=True,
                      cover_image_url="u", images=["u"], price=5, currency="PKR", revision=1, created_at=NOW, updated_at=NOW)
    product.variants = [Variant(id=vid, product_id=pid, position=0, name="V", size="Free Size", image_url="u", price=5,
                                currency="PKR", stock=0, stock_status="Out of stock", is_active=True)]
    body = ProductResponseSchema.model_validate(product, from_attributes=True).model_dump(mode="json", by_alias=True)
    assert body["_id"] == str(pid) and body["variants"][0]["_id"] == str(vid)
    assert body["variants"][0]["stock_status"] == "Out of stock" and body["status"] == "active"


def test_staged_response_reads_orm_rows_including_the_audit_trail():
    sid = uuid.uuid4()
    row = StagedProduct(id=sid, source_id="p", source_name="P", source_url="https://s/1", source_content_hash="h",
                        dedupe_key="id:1", fetched_at=NOW, normalized_at=NOW, status="pending_review", product={"name": "x"},
                        source_attributes={}, missing_fields=["price"], stock_known=False, created_at=NOW, updated_at=NOW,
                        ingestion_job_id=None, product_id=None)
    row.__dict__["audit"] = [StagedProductAudit(staged_product_id=sid, at=NOW, action="staged", to_status="pending_review", actor="ingestion")]
    body = StagedProductResponse.model_validate(row, from_attributes=True).model_dump(mode="json", by_alias=True)
    assert body["_id"] == str(sid) and body["ingestion_job_id"] is None and body["product_id"] is None
    assert body["audit"][0]["action"] == "staged" and body["audit"][0]["actor"] == "ingestion"


def test_create_schema_still_validates_like_before():
    base = {"name": "N", "slug": "Good-Slug", "cover_image_url": "https://x/c.jpg", "variants": [variant_payload()]}
    created = ProductCreateSchema.model_validate(base)
    assert created.slug == "good-slug" and created.price == 10 and created.images == ["https://x/c.jpg"]
    for bad in ({"slug": "bad slug"}, {"variants": []}, {"category": "hats"}):
        with pytest.raises(ValueError):
            ProductCreateSchema.model_validate({**base, **bad})
