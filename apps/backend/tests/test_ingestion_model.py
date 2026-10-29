import pytest
from mongomock_motor import AsyncMongoMockClient
from pymongo.errors import DuplicateKeyError
from bson import ObjectId

from database.db import ensure_indexes
from models.ingestion_model import build_staged_document, content_hash
from schemas.ingestion_schema import STAGED_TRANSITIONS, StagedStatus, can_transition


def staged(**over):
    base = dict(
        source_id="s1", source_name="Source", source_url="https://shop.test/products/a",
        source_product_id=None, source_content_hash="h", fetched_at=__import__("datetime").datetime.now(),
        ingestion_job_id=ObjectId(), source_price=10.0, source_currency="AUD",
        product={"name": "A"}, source_attributes={}, missing_fields=["price"],
    )
    base.update(over)
    return build_staged_document(**base)


def test_staged_document_has_all_provenance_and_is_pending():
    doc = staged()
    for key in ("source_name", "source_url", "source_product_id", "source_content_hash", "fetched_at",
                "normalized_at", "ingestion_job_id", "source_price", "source_currency", "status",
                "rejection_reason", "created_at", "updated_at"):
        assert key in doc
    assert doc["status"] == "pending_review"
    assert doc["stock_known"] is False


def test_dedupe_key_prefers_source_product_id():
    assert staged(source_product_id="42")["dedupe_key"] == "id:42"
    assert staged()["dedupe_key"] == "url:https://shop.test/products/a"


def test_content_hash_is_stable_and_change_sensitive():
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})
    assert content_hash({"a": 1}) != content_hash({"a": 2})


def test_staged_cannot_skip_to_published():
    assert not can_transition(StagedStatus.PENDING_REVIEW, StagedStatus.PUBLISHED)
    assert not can_transition(StagedStatus.REJECTED, StagedStatus.PUBLISHED)
    assert can_transition(StagedStatus.APPROVED, StagedStatus.PUBLISHED)
    assert STAGED_TRANSITIONS[StagedStatus.ARCHIVED] == set()


@pytest.mark.asyncio
async def test_unique_index_blocks_duplicate_source_identity():
    db = AsyncMongoMockClient().t
    await ensure_indexes(db)
    await db.staged_products.insert_one(staged())
    with pytest.raises(DuplicateKeyError):
        await db.staged_products.insert_one(staged())
