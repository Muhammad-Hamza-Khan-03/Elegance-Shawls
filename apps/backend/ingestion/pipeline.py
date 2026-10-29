import uuid
from datetime import datetime, timezone

from pydantic import ValidationError

from configuration.config import settings
from ingestion.normalize import (
    InvalidSourceData, extract_source_product_id, normalize, source_url_for_path,
)
from ingestion.quill_scraper import FieldExtractor, ProductShawl, fetch_product_page_clean_html, html_to_text
from ingestion.safe_fetch import SafeFetcher, SourcePolicy
from repositories import staged as staged_repo


async def stage_product(sessions, normalized: dict, *, job_id: uuid.UUID | None, source_id: str,
                        source_name: str) -> tuple:
    """Idempotent upsert keyed by (source_id, source_product_id | source_url), in its own short transaction.

    Returns (row, outcome) where outcome is created | unchanged | updated | source_changed.
    Reviewed products (anything past pending_review) are never overwritten by a re-scrape.
    """
    async with sessions() as session, session.begin():
        return await staged_repo.stage_product(
            session, source_id=source_id, source_name=source_name, ingestion_job_id=job_id,
            **{k: normalized[k] for k in (
                "source_url", "source_product_id", "source_content_hash", "fetched_at", "source_price",
                "source_currency", "product", "source_attributes", "missing_fields")},
        )


async def run_job(
    sessions, job, *, fetcher: SafeFetcher, extractor: FieldExtractor, policy: SourcePolicy | None = None,
) -> dict:
    """Fetch -> extract -> normalize -> stage. Raises on failure; the worker classifies errors.

    No database transaction is open while the page is fetched or extracted.
    """
    policy = policy or fetcher.policy
    url = source_url_for_path(job.path, policy)

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
        sessions, normalized, job_id=job.id, source_id=job.source_id,
        source_name=settings.ingestion_source_name or policy.domain,
    )
    return {"staged_product_id": str(staged.id), "outcome": outcome}
