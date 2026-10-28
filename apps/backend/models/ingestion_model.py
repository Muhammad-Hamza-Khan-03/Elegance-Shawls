import hashlib
import json
from datetime import datetime, timezone

from bson import ObjectId

from schemas.ingestion_schema import StagedStatus


def now() -> datetime:
    return datetime.now(timezone.utc)


def content_hash(payload: dict) -> str:
    """Stable hash of source-derived content, used to detect changes between runs."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def audit_entry(action: str, from_status=None, to_status=None, actor="admin", note=None) -> dict:
    return {
        "at": now(),
        "action": action,
        "from_status": from_status,
        "to_status": to_status,
        "actor": actor,
        "note": note,
    }


def build_staged_document(
    *,
    source_id: str,
    source_name: str,
    source_url: str,
    source_product_id: str | None,
    source_content_hash: str,
    fetched_at: datetime,
    ingestion_job_id: ObjectId,
    source_price: float | None,
    source_currency: str | None,
    product: dict,
    source_attributes: dict,
    missing_fields: list[str],
) -> dict:
    ts = now()
    return {
        "_id": ObjectId(),
        "source_id": source_id,
        "source_name": source_name,
        "source_url": source_url,
        "source_product_id": source_product_id,
        "source_content_hash": source_content_hash,
        # Identity used for duplicate protection: the source's own id when it has one.
        "dedupe_key": f"id:{source_product_id}" if source_product_id else f"url:{source_url}",
        "fetched_at": fetched_at,
        "normalized_at": ts,
        "ingestion_job_id": ingestion_job_id,
        "source_price": source_price,
        "source_currency": source_currency,
        "status": StagedStatus.PENDING_REVIEW.value,
        "rejection_reason": None,
        "created_at": ts,
        "updated_at": ts,
        "product": product,
        "source_attributes": source_attributes,
        "missing_fields": missing_fields,
        # No scraper supplies inventory, so stock is never "known" from the source.
        "stock_known": False,
        "product_id": None,
        "audit": [audit_entry("staged", to_status=StagedStatus.PENDING_REVIEW.value, actor="ingestion")],
    }
