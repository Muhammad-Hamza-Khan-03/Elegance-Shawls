"""Staged-product repository: ingestion staging, human review and the review audit trail.

Nothing here makes a product public except `publish`, which a human triggers explicitly and which
only moves a product that `approve` already created as a draft. Callers own the transaction.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.relational_model import StagedProduct, StagedProductAudit
from repositories import Conflict, InvalidDraft, InvalidTransition, NotFound, ProductUnavailable
from repositories import products as catalogue
from repositories.products import ProductInput, VariantInput
from schemas.ingestion_schema import StagedStatus, can_transition

S = StagedStatus
Key = tuple[datetime, uuid.UUID]
CATALOGUE_FIELDS = ("name", "slug", "cover_image_url", "images", "main_description", "category", "material", "sizing", "weight")
SOURCE_CHANGED_NOTE = "Source changed after review; not applied"


@dataclass
class Page:
    items: list[StagedProduct]
    next_after: Key | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _audit(session: AsyncSession, staged_id: uuid.UUID, action: str, *, from_status: str | None = None,
                 to_status: str | None = None, actor: str = "admin", note: str | None = None) -> None:
    session.add(StagedProductAudit(staged_product_id=staged_id, action=action, from_status=from_status,
                                   to_status=to_status, actor=actor, note=note))
    await session.flush()


async def reload(session: AsyncSession, staged_id: uuid.UUID) -> StagedProduct | None:
    return await session.get(StagedProduct, staged_id, populate_existing=True)


async def _locked(session: AsyncSession, staged_id: uuid.UUID) -> StagedProduct:
    """Row lock: concurrent actions on the same staged product are serialised, so a transition is a real compare-and-set."""
    row = (await session.execute(
        select(StagedProduct).where(StagedProduct.id == staged_id).with_for_update()
        .execution_options(populate_existing=True))).scalar_one_or_none()
    if row is None:
        raise NotFound("Staged product not found")
    return row


async def get_staged(session: AsyncSession, staged_id: uuid.UUID) -> StagedProduct | None:
    return await session.get(StagedProduct, staged_id)


async def list_staged(session: AsyncSession, *, status: str | None, limit: int, after: Key | None = None) -> Page:
    stmt = select(StagedProduct).order_by(StagedProduct.created_at.desc(), StagedProduct.id.desc()).limit(limit + 1)
    if status:
        stmt = stmt.where(StagedProduct.status == status)
    if after is not None:
        stmt = stmt.where(tuple_(StagedProduct.created_at, StagedProduct.id) < tuple_(*after))
    rows = list((await session.execute(stmt)).scalars())
    if len(rows) <= limit:
        return Page(rows, None)
    rows.pop()
    return Page(rows, (rows[-1].created_at, rows[-1].id))


# ---- staging (ingestion side) ----------------------------------------------------------------
async def stage_product(
    session: AsyncSession, *, source_id: str, source_name: str, source_url: str, source_product_id: str | None,
    source_content_hash: str, fetched_at: datetime, ingestion_job_id: uuid.UUID | None,
    source_price: Decimal | float | None, source_currency: str | None, product: dict, source_attributes: dict,
    missing_fields: list[str],
) -> tuple[StagedProduct, str]:
    """Idempotent upsert keyed by (source_id, source_product_id | source_url).

    Returns (row, outcome) with outcome created | unchanged | updated | source_changed. Anything past
    pending_review is never overwritten by a re-scrape; the change is only flagged for the reviewer.
    """
    ts = _now()
    dedupe_key = f"id:{source_product_id}" if source_product_id else f"url:{source_url}"
    values = {
        "source_id": source_id, "source_name": source_name, "source_url": source_url,
        "source_product_id": source_product_id, "source_content_hash": source_content_hash,
        "dedupe_key": dedupe_key, "fetched_at": fetched_at, "normalized_at": ts, "ingestion_job_id": ingestion_job_id,
        "source_price": source_price, "source_currency": source_currency, "product": product,
        "source_attributes": source_attributes, "missing_fields": missing_fields,
        # No scraper supplies inventory, so stock is never "known" from the source.
        "stock_known": False,
    }
    inserted = (await session.execute(
        pg_insert(StagedProduct).values(**values)
        .on_conflict_do_nothing(index_elements=["source_id", "dedupe_key"]).returning(StagedProduct.id))).scalar_one_or_none()
    if inserted is not None:
        await _audit(session, inserted, "staged", to_status=S.PENDING_REVIEW.value, actor="ingestion")
        return await reload(session, inserted), "created"

    # A concurrent stager's uncommitted row makes the INSERT wait, so by here the row is visible and lockable.
    existing = (await session.execute(
        select(StagedProduct).where(StagedProduct.source_id == source_id, StagedProduct.dedupe_key == dedupe_key)
        .with_for_update().execution_options(populate_existing=True))).scalar_one()
    if existing.source_content_hash == source_content_hash:
        return existing, "unchanged"
    if existing.status == S.PENDING_REVIEW.value:
        for name in ("source_url", "source_content_hash", "fetched_at", "normalized_at", "ingestion_job_id",
                     "source_price", "source_currency", "product", "source_attributes", "missing_fields"):
            setattr(existing, name, values[name])
        existing.updated_at = func.now()
        await session.flush()
        await _audit(session, existing.id, "source_updated", actor="ingestion")
        return await reload(session, existing.id), "updated"
    existing.latest_source_hash = source_content_hash
    existing.updated_at = func.now()
    await session.flush()
    await _audit(session, existing.id, "source_changed", actor="ingestion", note=SOURCE_CHANGED_NOTE)
    return await reload(session, existing.id), "source_changed"


# ---- review actions (human side) -------------------------------------------------------------
async def transition(session: AsyncSession, staged_id: uuid.UUID, target: StagedStatus, action: str, *,
                     set_fields: dict | None = None, note: str | None = None, actor: str = "admin") -> StagedProduct:
    """Move to `target` if, and only if, the workflow allows it from the CURRENT status (checked under a row lock)."""
    row = await _locked(session, staged_id)
    current = StagedStatus(row.status)
    if not can_transition(current, target):
        raise InvalidTransition(current.value, target.value)
    for name, value in (set_fields or {}).items():
        setattr(row, name, value)
    row.status = target.value
    row.updated_at = func.now()
    await session.flush()
    await _audit(session, staged_id, action, from_status=current.value, to_status=target.value, actor=actor, note=note)
    return await reload(session, staged_id)


async def reject(session: AsyncSession, staged_id: uuid.UUID, reason: str, *, actor: str = "admin") -> StagedProduct:
    reason = reason.strip()
    if len(reason) < 3:
        raise InvalidDraft("A rejection needs a reason of at least 3 characters")
    async with session.begin_nested():
        return await transition(session, staged_id, S.REJECTED, "reject", set_fields={"rejection_reason": reason},
                                note=reason, actor=actor)


def _draft_to_input(draft: dict, price: int, stock: int) -> ProductInput:
    try:
        return ProductInput(
            **{k: draft[k] for k in CATALOGUE_FIELDS if k in draft and draft[k] is not None},
            price=price, currency="PKR", status="draft",  # approve always creates a DRAFT; publishing is separate
            variants=[VariantInput(name=v["name"], color=v.get("color"), size=v.get("size") or "Free Size",
                                   image_url=v["image_url"], price=price, stock=stock) for v in draft["variants"]],
        )
    except (KeyError, TypeError) as exc:
        raise InvalidDraft(f"Staged product is missing {exc}") from exc


async def approve(session: AsyncSession, staged_id: uuid.UUID, *, price: int, stock: int = 0,
                  actor: str = "admin") -> StagedProduct:
    """Approve into a DRAFT catalogue product (with variants) in ONE savepoint.

    The reviewer supplies what the source cannot: the PKR price and the stock. A duplicate slug or an
    invalid draft undoes everything, leaving the staged product pending_review exactly as before.
    """
    if price < 0 or stock < 0:
        raise InvalidDraft("Price and stock cannot be negative")
    async with session.begin_nested():
        row = await _locked(session, staged_id)
        current = StagedStatus(row.status)
        if not can_transition(current, S.APPROVED):
            raise InvalidTransition(current.value, S.APPROVED.value)
        created = await catalogue.create_product(session, _draft_to_input(row.product, price, stock))
        row.status = S.APPROVED.value
        row.product_id = created.id
        row.stock_known = True
        row.approved_price, row.approved_stock = price, stock
        row.missing_fields = [f for f in row.missing_fields if f not in ("price", "stock")]
        row.updated_at = func.now()
        await session.flush()
        await _audit(session, staged_id, "approve", from_status=current.value, to_status=S.APPROVED.value, actor=actor)
    return await reload(session, staged_id)


async def publish(session: AsyncSession, staged_id: uuid.UUID, *, actor: str) -> StagedProduct:
    """The only path to a public ingested product. `actor` is mandatory: a human performs this."""
    if not actor:
        raise Conflict("Publishing requires an identified actor")
    async with session.begin_nested():  # a missing/archived product undoes the status change
        staged = await transition(session, staged_id, S.PUBLISHED, "publish", actor=actor)
        if staged.product_id is None or not await catalogue.set_state_unless_archived(session, staged.product_id, "active"):
            raise ProductUnavailable("Catalogue product is missing or archived")
    return await reload(session, staged_id)


async def unpublish(session: AsyncSession, staged_id: uuid.UUID, *, actor: str = "admin") -> StagedProduct:
    async with session.begin_nested():
        staged = await transition(session, staged_id, S.UNPUBLISHED, "unpublish", actor=actor)
        if staged.product_id is not None:
            await catalogue.set_state_unless_archived(session, staged.product_id, "draft")
    return await reload(session, staged_id)


async def archive(session: AsyncSession, staged_id: uuid.UUID, *, actor: str = "admin") -> StagedProduct:
    async with session.begin_nested():
        staged = await transition(session, staged_id, S.ARCHIVED, "archive", actor=actor)
        if staged.product_id is not None:
            await catalogue.set_state_unless_archived(session, staged.product_id, "archived")
    return await reload(session, staged_id)
