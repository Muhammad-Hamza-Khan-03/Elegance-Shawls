from datetime import datetime, timezone

from bson import ObjectId
from pydantic import ValidationError
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from configuration.config import settings
from ingestion.normalize import (
    InvalidSourceData, extract_source_product_id, normalize, source_url_for_path,
)
from ingestion.quill_scraper import FieldExtractor, ProductShawl, fetch_product_page_clean_html, html_to_text
from ingestion.safe_fetch import SafeFetcher, SourcePolicy
from models.ingestion_model import audit_entry, build_staged_document, now
from schemas.ingestion_schema import StagedStatus


async def stage_product(db, normalized: dict, *, job_id: ObjectId, source_id: str, source_name: str) -> tuple[dict, str]:
    """Idempotent upsert keyed by (source_id, source_product_id | source_url).

    Returns (document, outcome) where outcome is created | unchanged | updated | source_changed.
    Reviewed products (anything past pending_review) are never overwritten by a re-scrape.
    """
    document = build_staged_document(
        source_id=source_id, source_name=source_name, ingestion_job_id=job_id,
        **{k: normalized[k] for k in (
            "source_url", "source_product_id", "source_content_hash", "fetched_at", "source_price",
            "source_currency", "product", "source_attributes", "missing_fields")},
    )
    try:
        await db.staged_products.insert_one(document)
        return document, "created"
    except DuplicateKeyError:
        pass

    key = {"source_id": source_id, "dedupe_key": document["dedupe_key"]}
    existing = await db.staged_products.find_one(key)
    if existing["source_content_hash"] == normalized["source_content_hash"]:
        return existing, "unchanged"

    ts = now()
    if existing["status"] == StagedStatus.PENDING_REVIEW.value:
        updated = await db.staged_products.find_one_and_update(
            {**key, "status": StagedStatus.PENDING_REVIEW.value},
            {"$set": {
                "source_url": document["source_url"], "source_content_hash": document["source_content_hash"],
                "fetched_at": document["fetched_at"], "normalized_at": document["normalized_at"],
                "ingestion_job_id": job_id, "source_price": document["source_price"],
                "source_currency": document["source_currency"], "product": document["product"],
                "source_attributes": document["source_attributes"],
                "missing_fields": document["missing_fields"], "updated_at": ts,
            }, "$push": {"audit": audit_entry("source_updated", actor="ingestion")}},
            return_document=ReturnDocument.AFTER,
        )
        if updated:
            return updated, "updated"

    flagged = await db.staged_products.find_one_and_update(
        key,
        {"$set": {"latest_source_hash": normalized["source_content_hash"], "updated_at": ts},
         "$push": {"audit": audit_entry("source_changed", actor="ingestion",
                                        note="Source changed after review; not applied")}},
        return_document=ReturnDocument.AFTER,
    )
    return flagged, "source_changed"


async def run_job(
    db, job: dict, *, fetcher: SafeFetcher, extractor: FieldExtractor, policy: SourcePolicy | None = None,
) -> dict:
    """Fetch -> extract -> normalize -> stage. Raises on failure; the worker classifies errors."""
    policy = policy or fetcher.policy
    url = source_url_for_path(job["path"], policy)

    page = await fetch_product_page_clean_html(fetcher, url)
    if not page:
        raise InvalidSourceData("Source page was empty")
    fetched_at = datetime.now(timezone.utc)

    extracted = await extractor.extract(
        source_url=page["source_url"], sanitized_html=page["html"], text=html_to_text(page["html"]),
        raw_html=page["raw_html"],
    )
    if not isinstance(extracted, dict):
        raise InvalidSourceData("Extractor returned no product data")
    # Page-derived facts win: never trust an extractor for the URL, and merge scraped images.
    merged_images = list(dict.fromkeys([*page["images"], *extracted.get("image_urls", [])]))
    try:
        scraped = ProductShawl.model_validate({**extracted, "url": page["source_url"], "image_urls": merged_images})
    except ValidationError as exc:
        fields = ", ".join(sorted({".".join(map(str, e["loc"])) for e in exc.errors()}))
        raise InvalidSourceData(f"Invalid scraper output: {fields}") from exc

    normalized = normalize(
        scraped, policy=policy, source_product_id=extract_source_product_id(page["raw_html"]),
        fetched_at=fetched_at,
    )
    staged, outcome = await stage_product(
        db, normalized, job_id=job["_id"], source_id=job["source_id"],
        source_name=settings.ingestion_source_name or policy.domain,
    )
    return {"staged_product_id": str(staged["_id"]), "outcome": outcome}
