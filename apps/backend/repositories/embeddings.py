"""Embedding rows (product and variant): idempotent create, leased claim, conditional completion and the active predicate.
Callers own the transaction (no commits).

A row is both the job and its result. Every state change is conditional on the lease owner, so a worker that lost its
lease (or whose source moved on) can never overwrite a newer outcome. Old vectors are kept; `active_select` plus the hash
check in `embedding_service.active_embeddings` define "searchable now".
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.relational_model import EMBEDDING_KEY, Product, ProductEmbedding, Variant, VariantEmbedding

MAX_ERROR_LENGTH = 300
KINDS = {"product": ProductEmbedding, "variant": VariantEmbedding}
_VERSION_COLUMNS = ("representation_version", "provider", "model", "model_revision", "index_version")


def model_for(kind: str):
    try:
        return KINDS[kind]
    except KeyError:
        raise ValueError(f"unknown embedding kind {kind!r}") from None


def _owner_column(kind: str):
    model = model_for(kind)
    return model.product_id if kind == "product" else model.variant_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get(session: AsyncSession, kind: str, row_id: uuid.UUID):
    return await session.get(model_for(kind), row_id, populate_existing=True)


async def upsert_pending(session: AsyncSession, kind: str, *, owner_id: uuid.UUID, product_id: uuid.UUID, key: dict,
                         max_attempts: int):
    """Insert a queued row for the identity key, or return the existing one (any status): (row, created)."""
    model = model_for(kind)
    owner = {"product_id": product_id} if kind == "product" else {"variant_id": owner_id, "product_id": product_id}
    values = {**owner, **{k: key[k] for k in EMBEDDING_KEY}, "max_attempts": max_attempts}
    created_id = (await session.execute(pg_insert(model).values(**values).on_conflict_do_nothing().returning(model.id))
                  ).scalar_one_or_none()
    if created_id is not None:
        return await get(session, kind, created_id), True
    where = [_owner_column(kind) == owner_id, *(getattr(model, k) == key[k] for k in EMBEDDING_KEY)]
    return (await session.execute(select(model).where(*where))).scalar_one(), False


async def claim(session: AsyncSession, kind: str, row_id: uuid.UUID, lease_owner: str, lease_seconds: int):
    """queued (due) or expired-lease running -> running with one more attempt; None when not claimable.

    An abandoned lease that has already used every attempt becomes terminally failed instead of being claimed again.
    """
    model = model_for(kind)
    await session.execute(
        update(model).where(model.id == row_id, model.status == "running", model.lease_expires_at < func.now(),
                            model.attempts >= model.max_attempts)
        .values(status="failed", last_error="lease expired after the last attempt", last_error_retryable=False,
                lease_owner=None, lease_expires_at=None, finished_at=func.now(), updated_at=func.now()))
    claimable = (((model.status == "queued") & (model.available_at <= func.now()))
                 | ((model.status == "running") & (model.lease_expires_at < func.now())))
    found = (await session.execute(
        update(model).where(model.id == row_id, model.attempts < model.max_attempts, claimable)
        .values(status="running", attempts=model.attempts + 1, lease_owner=lease_owner,
                lease_expires_at=func.now() + timedelta(seconds=lease_seconds), started_at=func.now(), updated_at=func.now())
        .returning(model.id))).scalar_one_or_none()
    return await get(session, kind, found) if found else None


async def complete(session: AsyncSession, kind: str, row_id: uuid.UUID, lease_owner: str, vector: list[float]):
    """running -> succeeded for the lease holder only, then the owner's older succeeded rows of the same version go stale."""
    model = model_for(kind)
    found = (await session.execute(
        update(model).where(model.id == row_id, model.status == "running", model.lease_owner == lease_owner)
        .values(status="succeeded", embedding=vector, lease_owner=None, lease_expires_at=None, last_error=None,
                last_error_retryable=None, finished_at=func.now(), updated_at=func.now())
        .returning(model.id))).scalar_one_or_none()
    if found is None:
        return None
    row = await get(session, kind, row_id)
    await session.execute(
        update(model).where(_owner_column(kind) == getattr(row, "variant_id" if kind == "variant" else "product_id"),
                            model.id != row_id, model.status == "succeeded",
                            *(getattr(model, c) == getattr(row, c) for c in _VERSION_COLUMNS))
        .values(status="stale", updated_at=func.now()))
    return row


async def finish(session: AsyncSession, kind: str, row_id: uuid.UUID, lease_owner: str, *, status: str,
                 error: str | None = None, retryable: bool | None = None, delay_seconds: float = 0):
    """running -> failed | stale (terminal) or queued (retry after delay) for the lease holder only; None if the lease is gone."""
    model = model_for(kind)
    values = {"status": status, "last_error": error[:MAX_ERROR_LENGTH] if error else None, "last_error_retryable": retryable,
              "lease_owner": None, "lease_expires_at": None, "updated_at": func.now()}
    if status == "queued":
        values["available_at"] = func.now() + timedelta(seconds=delay_seconds)
    else:
        values["finished_at"] = func.now()
    found = (await session.execute(
        update(model).where(model.id == row_id, model.status == "running", model.lease_owner == lease_owner)
        .values(**values).returning(model.id))).scalar_one_or_none()
    return await get(session, kind, found) if found else None


def active_select(kind: str, *, representation_version: str, provider: str, model: str, model_revision: str,
                  index_version: str):
    """SQL prefilter of what is searchable: succeeded, current revision, active version, still public.

    It cannot see the representation hash; search.embedding_service.active_embeddings applies the full predicate."""
    emb = model_for(kind)
    stmt = select(emb).join(Product, Product.id == emb.product_id).where(
        emb.status == "succeeded", emb.source_revision == Product.revision, Product.status == "active",
        emb.representation_version == representation_version, emb.provider == provider, emb.model == model,
        emb.model_revision == model_revision, emb.index_version == index_version)
    if kind == "variant":
        stmt = stmt.join(Variant, Variant.id == emb.variant_id).where(Variant.is_active)
    return stmt


async def live_owner_ids(session: AsyncSession, kind: str, after: uuid.UUID | None, limit: int) -> list[uuid.UUID]:
    """Public live products (or active variants of them) in id order, after a resume cursor: a bounded keyset page."""
    if kind == "product":
        stmt = select(Product.id).where(Product.status == "active")
        column = Product.id
    else:
        stmt = select(Variant.id).join(Product, Product.id == Variant.product_id).where(Product.status == "active", Variant.is_active)
        column = Variant.id
    if after is not None:
        stmt = stmt.where(column > after)
    return list((await session.execute(stmt.order_by(column).limit(limit))).scalars())
