"""Embeds public catalogue representations (S4a) into pgvector rows. It reads catalogue rows and writes only embedding rows.

Every step re-reads the live source: a row whose product or variant is no longer public, or whose revision or
representation hash changed, ends as `stale` without a vector, and the completion re-checks under a row lock so a slow
provider call can never publish a vector for an outdated source. The provider is always called through embed_checked.
"""
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.relational_model import EMBEDDING_DIMENSIONS, Product, Variant
from repositories import embeddings as repo
from repositories.attributes import list_attributes
from search.providers import EmbeddingProvider, NonRetryableEmbeddingError, classify, embed_checked
from search.representations import Representation, product_representation, variant_representation

logger = logging.getLogger("elegance.embeddings")


@dataclass(frozen=True)
class Source:
    product_id: uuid.UUID
    revision: int  # the product's revision; variants have none of their own
    representation: Representation


def provider_identity(provider: EmbeddingProvider) -> dict:
    return {"provider": provider.name, "model": provider.model, "model_revision": getattr(provider, "model_revision", "")}


async def load_source(session: AsyncSession, kind: str, owner_id: uuid.UUID, *, lock: bool = False) -> Source | None:
    """The current representation of a public live product or variant, else None. `lock` takes FOR SHARE row locks."""
    if kind == "product":
        stmt = select(Product.id, Product.revision, Product.name, Product.category, Product.material,
                      Product.main_description).where(Product.id == owner_id, Product.status == "active")
    else:
        stmt = (select(Product.id, Product.revision, Product.name, Product.category, Product.material, Variant.name.label("variant"),
                       Variant.color).join(Variant, Variant.product_id == Product.id)
                .where(Variant.id == owner_id, Product.status == "active", Variant.is_active))
    row = (await session.execute(stmt.with_for_update(read=True) if lock else stmt)).first()
    if row is None:
        return None
    wanted = None if kind == "product" else owner_id
    attributes = [a for a in await list_attributes(session, [row.id]) if a.variant_id == wanted]
    if kind == "product":
        rep = product_representation(row.name, row.category, row.material, row.main_description, attributes)
    else:
        rep = variant_representation(row.name, row.variant, row.color, row.category, row.material, attributes)
    return Source(row.id, row.revision, rep)


def _key(source: Source, provider: EmbeddingProvider, index_version: str) -> dict:
    return {"source_revision": source.revision, "representation_version": source.representation.version,
            "representation_hash": source.representation.sha256, "index_version": index_version, **provider_identity(provider)}


async def ensure_pending(session: AsyncSession, kind: str, owner_id: uuid.UUID, provider: EmbeddingProvider, *,
                         index_version: str, max_attempts: int):
    """(row, created) for the owner's current representation, or (None, False) when it is not public.

    Raises ValueError (RepresentationTooLong included) when the catalogue text cannot be represented.
    """
    source = await load_source(session, kind, owner_id)
    if source is None:
        return None, False
    return await repo.upsert_pending(session, kind, owner_id=owner_id, product_id=source.product_id,
                                     key=_key(source, provider, index_version), max_attempts=max_attempts)


def _owner_id(kind: str, row) -> uuid.UUID:
    return row.product_id if kind == "product" else row.variant_id


def _matches(source: Source | None, row) -> bool:
    return (source is not None and source.revision == row.source_revision
            and source.representation.sha256 == row.representation_hash
            and source.representation.version == row.representation_version)


async def process(sessions: async_sessionmaker, provider: EmbeddingProvider, kind: str, row_id: uuid.UUID, *,
                  lease_seconds: int, backoff_seconds: float, lease_owner: str | None = None) -> dict:
    """Claim one row and embed it. Returns {"status": succeeded|stale|failed|retry|skipped|lease_lost[, "delay": s]}.

    Never raises for provider or source problems; they are recorded on the row. Never writes anything but the row.
    """
    lease_owner = lease_owner or uuid.uuid4().hex

    async def settle(**kw):  # conditional on our lease: None means someone else owns the row now
        async with sessions() as s, s.begin():
            return await repo.finish(s, kind, row_id, lease_owner, **kw)

    async with sessions() as s, s.begin():
        row = await repo.claim(s, kind, row_id, lease_owner, lease_seconds)
    if row is None:
        return {"status": "skipped"}
    try:
        async with sessions() as s, s.begin():
            source = await load_source(s, kind, _owner_id(kind, row))
    except ValueError as exc:  # catalogue text that cannot be represented
        await settle(status="failed", error=f"representation: {exc}", retryable=False)
        return {"status": "failed"}
    if not _matches(source, row):
        await settle(status="stale", error="source changed or no longer public")
        return {"status": "stale"}

    try:
        if (provider_identity(provider) != {k: getattr(row, k) for k in ("provider", "model", "model_revision")}
                or provider.dimensions != EMBEDDING_DIMENSIONS):
            raise NonRetryableEmbeddingError("provider identity or dimensions do not match the row and the vector column")
        [vector] = await embed_checked(provider, [source.representation.text])
    except Exception as exc:
        err = classify(exc)
        retry = err.retryable and row.attempts < row.max_attempts
        delay = backoff_seconds * 2 ** (row.attempts - 1)
        logger.warning("embedding %s failed kind=%s retry=%s: %s", row_id, kind, retry, type(err).__name__)
        await settle(status="queued" if retry else "failed", error=str(err), retryable=err.retryable, delay_seconds=delay)
        return {"status": "retry", "delay": delay} if retry else {"status": "failed"}

    async with sessions() as s, s.begin():
        current = await load_source(s, kind, _owner_id(kind, row), lock=True)
        if not _matches(current, row):
            done = await repo.finish(s, kind, row_id, lease_owner, status="stale", error="source changed during embedding")
            return {"status": "stale" if done else "lease_lost"}
        done = await repo.complete(s, kind, row_id, lease_owner, vector)
    return {"status": "succeeded" if done else "lease_lost"}


async def active_embeddings(session: AsyncSession, kind: str, *, representation_version: str, provider: str, model: str,
                            model_revision: str, index_version: str) -> list:
    """Embeddings searchable right now. The SQL prefilter cannot see the representation hash, so each candidate is
    checked against the live source with the canonical S4a builder: a content change at the same revision drops the
    old vector at once, before any replacement completes.
    shortcut: one source read per candidate; store the hash on the owner if a search route needs this in one SQL query."""
    candidates = (await session.execute(repo.active_select(
        kind, representation_version=representation_version, provider=provider, model=model,
        model_revision=model_revision, index_version=index_version))).scalars().all()
    rows = []
    for row in candidates:
        try:
            source = await load_source(session, kind, _owner_id(kind, row))
        except ValueError:  # text that can no longer be represented has no valid vector
            continue
        if _matches(source, row):
            rows.append(row)
    return rows
