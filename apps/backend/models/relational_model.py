"""PostgreSQL relational schema (issues #95, S1): the sole source of truth for the catalogue, ingestion and platform tables.

Enums are constrained text (CHECK), timestamps are timezone-aware UTC, IDs are UUIDs.
Memory, embeddings, voice, enrichment, enquiries and the catalogue are later phases.
"""
import uuid
from datetime import datetime

from decimal import Decimal

from sqlalchemy import (
    ARRAY, CHAR, BigInteger, Boolean, CheckConstraint, Computed, DateTime, ForeignKey, ForeignKeyConstraint, Identity, Index, Integer, MetaData, Numeric, Text,
    UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

CUSTOMER_STATUSES = ("anonymous", "registered")
IDENTITY_PROVIDERS = ("anon", "google", "phone")
CONVERSATION_CHANNELS = ("web", "admin")
MESSAGE_ROLES = ("user", "assistant", "system", "tool")
MESSAGE_SCRIPTS = ("en", "ur", "roman_ur")
TOOL_CALL_STATUSES = ("ok", "error", "rejected", "timeout")
EVENT_TYPES = ("view", "search", "impression", "click", "add_to_cart", "ui_action", "voice", "handoff")
ACTOR_TYPES = ("system", "admin", "customer", "agent")
OUTBOX_AGGREGATES = ("product", "variant")
OUTBOX_EVENT_TYPES = ("created", "updated", "archived")
PRODUCT_CATEGORIES = ("shawls", "stoles", "scarves")
PRODUCT_STATUSES = ("active", "draft", "out_of_stock", "archived")
JOB_STATUSES = ("queued", "running", "succeeded", "retrying", "failed", "cancelled")
STAGED_STATUSES = ("pending_review", "approved", "rejected", "published", "unpublished", "archived")
ATTRIBUTE_KEYS = ("color_name", "color_family", "fabric", "composition", "pattern", "occasion", "season", "style", "authenticity")
ATTRIBUTE_SOURCES = ("visual_suggestion", "supplier_declared", "staff_approved", "imported")
ENRICHMENT_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
# States that only exist once a reviewer has approved a price and a catalogue product has been created.
STAGED_APPROVED_STATES = ("approved", "published", "unpublished")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (CheckConstraint(_in("status", CUSTOMER_STATUSES), name="status"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="anonymous")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CustomerIdentity(Base):
    __tablename__ = "customer_identities"
    __table_args__ = (
        CheckConstraint(_in("provider", IDENTITY_PROVIDERS), name="provider"),
        UniqueConstraint("provider", "subject"),
        Index("ix_customer_identities_customer_id", "customer_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(_in("channel", CONVERSATION_CHANNELS), name="channel"),
        Index("ix_conversations_customer_id_started_at", "customer_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Deleting a customer deletes their conversations (retention and deletion requests).
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(Text, nullable=False, server_default="web")
    prompt_version: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    index_version: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(_in("role", MESSAGE_ROLES), name="role"),
        CheckConstraint(_in("script", MESSAGE_SCRIPTS), name="script"),
        CheckConstraint("tokens >= 0", name="tokens_nonnegative"),
        CheckConstraint("latency_ms >= 0", name="latency_nonnegative"),
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    script: Mapped[str | None] = mapped_column(Text)
    tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()


class ToolCall(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        CheckConstraint(_in("status", TOOL_CALL_STATUSES), name="status"),
        CheckConstraint("duration_ms >= 0", name="duration_nonnegative"),
        Index("ix_tool_calls_message_id", "message_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    arguments: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    result_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(_in("type", EVENT_TYPES), name="type"),
        Index("ix_events_type_created_at", "type", "created_at"),
        Index("ix_events_customer_id_created_at", "customer_id", "created_at"),
        Index("ix_events_session_id_created_at", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Null until Phase 3 identity; deleting a customer keeps anonymised events.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _created_at()


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(_in("actor_type", ACTOR_TYPES), name="actor_type"),
        Index("ix_audit_log_created_at", "created_at"),
        Index("ix_audit_log_target_created_at", "target", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class Outbox(Base):
    """Change records written in the same transaction as a catalogue change; workers process them.

    Idempotent by (aggregate, aggregate_id, revision, event_type). aggregate_id is the product or
    variant UUID. Nothing writes here until the catalogue is on PostgreSQL; the table exists so the
    embedding worker has a durable contract.
    """
    __tablename__ = "outbox"
    __table_args__ = (
        CheckConstraint(_in("aggregate", OUTBOX_AGGREGATES), name="aggregate"),
        CheckConstraint(_in("event_type", OUTBOX_EVENT_TYPES), name="event_type"),
        CheckConstraint("revision >= 0", name="revision_nonnegative"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        UniqueConstraint("aggregate", "aggregate_id", "revision", "event_type"),
        # Workers poll only unprocessed rows, oldest first.
        Index("ix_outbox_unprocessed", "created_at", postgresql_where=text("processed_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    aggregate: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------------------------------------
# Catalogue, ingestion jobs and staged products
# --------------------------------------------------------------------------------------------
class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("slug"),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND char_length(slug) <= 180", name="slug_format"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 160", name="name_length"),
        CheckConstraint(_in("category", PRODUCT_CATEGORIES), name="category"),
        CheckConstraint(_in("status", PRODUCT_STATUSES), name="status"),
        CheckConstraint("cardinality(images) <= 12", name="images_max"),
        CheckConstraint("char_length(main_description) <= 5000", name="description_length"),
        CheckConstraint("char_length(material) <= 200 AND char_length(sizing) <= 200", name="material_sizing_length"),
        CheckConstraint("char_length(weight) <= 100 AND char_length(item_number) <= 100", name="weight_item_length"),
        CheckConstraint("price >= 0", name="price_nonnegative"),
        CheckConstraint("currency = upper(currency)", name="currency_upper"),
        CheckConstraint("revision >= 1", name="revision_positive"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False, server_default="shawls")
    # New rows are drafts unless a caller says otherwise: publishing is always a deliberate act.
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    # Public visibility is derived, so it can never contradict status.
    is_active: Mapped[bool] = mapped_column(Boolean, Computed("status = 'active'", persisted=True), nullable=False)
    cover_image_url: Mapped[str] = mapped_column(Text, nullable=False)
    images: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    main_description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="PKR")
    material: Mapped[str | None] = mapped_column(Text)
    sizing: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[str | None] = mapped_column(Text)
    item_number: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # Ordered by position; no schema change (relationship only). Removing a variant from the list deletes it.
    variants: Mapped[list["Variant"]] = relationship(
        "Variant", order_by="Variant.position", lazy="selectin", cascade="all, delete-orphan", passive_deletes=True
    )


# Public feed: newest first with a stable (created_at, id) cursor; only active rows are indexed.
Index("ix_products_public_feed", Product.created_at.desc(), Product.id.desc(), postgresql_where=text("status = 'active'"))
Index("ix_products_created_at_id", Product.created_at.desc(), Product.id.desc())   # admin list, all states
Index("ix_products_item_number", Product.item_number, postgresql_where=text("item_number IS NOT NULL"))


class Variant(Base):
    __tablename__ = "variants"
    __table_args__ = (
        # Deferred so a reorder inside one transaction can swap positions.
        UniqueConstraint("product_id", "position", deferrable=True, initially="DEFERRED"),
        UniqueConstraint("id", "product_id"),  # target of catalog_attributes' composite FK: a variant attribute stays in its own product
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("char_length(name) >= 1", name="name_present"),
        CheckConstraint("char_length(color) >= 1", name="color_not_empty"),
        CheckConstraint("price >= 0", name="price_nonnegative"),
        CheckConstraint("stock >= 0", name="stock_nonnegative"),
        CheckConstraint("currency = upper(currency)", name="currency_upper"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str | None] = mapped_column(Text)
    size: Mapped[str] = mapped_column(Text, nullable=False, server_default="Free Size")
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="PKR")
    stock: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Derived from stock, so the label can never contradict the count.
    stock_status: Mapped[str] = mapped_column(
        Text, Computed("CASE WHEN stock > 0 THEN 'In stock' ELSE 'Out of stock' END", persisted=True), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class CatalogAttribute(Base):
    """One normalised attribute of a product (variant_id NULL) or of one of its variants. value NULL = explicitly unknown."""
    __tablename__ = "catalog_attributes"
    __table_args__ = (
        ForeignKeyConstraint(["variant_id", "product_id"], ["variants.id", "variants.product_id"],
                             ondelete="CASCADE", name="fk_catalog_attributes_variant_id_variants"),
        CheckConstraint(_in("key", ATTRIBUTE_KEYS), name="key"),
        CheckConstraint(_in("source", ATTRIBUTE_SOURCES), name="source"),
        CheckConstraint("char_length(value) BETWEEN 1 AND 200", name="value_length"),
        CheckConstraint("char_length(model_version) BETWEEN 1 AND 100 AND char_length(approved_by) BETWEEN 1 AND 200",
                        name="provenance_length"),
        CheckConstraint(
            "(source = 'staff_approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL) "
            "OR (source <> 'staff_approved' AND approved_by IS NULL AND approved_at IS NULL)", name="approval"),
        Index("ix_catalog_attributes_product_key", "product_id", "key", unique=True, postgresql_where=text("variant_id IS NULL")),
        Index("ix_catalog_attributes_variant_key", "variant_id", "key", unique=True, postgresql_where=text("variant_id IS NOT NULL")),
        Index("ix_catalog_attributes_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        CheckConstraint(_in("status", JOB_STATUSES), name="status"),
        CheckConstraint("char_length(path) BETWEEN 1 AND 220", name="path_length"),
        CheckConstraint("attempts >= 0 AND max_attempts >= 1 AND attempts <= max_attempts", name="attempts_bounded"),
        # A running job always has an owner and a lease, so recovery can find abandoned work.
        CheckConstraint(
            "status <> 'running' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="lease_present_while_running",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(Text)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    last_error: Mapped[str | None] = mapped_column(Text)
    # Whether the last failure was classified retryable (NULL: no failure recorded).
    last_error_retryable: Mapped[bool | None] = mapped_column(Boolean)
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Workers poll only claimable rows; lease recovery scans only running rows; the admin list is newest first.
Index("ix_ingestion_jobs_claimable", IngestionJob.available_at,
      postgresql_where=text("status IN ('queued', 'retrying') AND NOT cancel_requested"))
Index("ix_ingestion_jobs_running_lease", IngestionJob.lease_expires_at, postgresql_where=text("status = 'running'"))
Index("ix_ingestion_jobs_created_at_id", IngestionJob.created_at.desc(), IngestionJob.id.desc())


class StagedProduct(Base):
    __tablename__ = "staged_products"
    __table_args__ = (
        UniqueConstraint("source_id", "dedupe_key"),
        CheckConstraint(_in("status", STAGED_STATUSES), name="status"),
        CheckConstraint("source_price >= 0", name="source_price_nonnegative"),
        CheckConstraint("approved_price >= 0 AND approved_stock >= 0", name="approved_nonnegative"),
        CheckConstraint("status <> 'rejected' OR (rejection_reason IS NOT NULL AND char_length(rejection_reason) >= 3)", name="rejection_needs_reason"),
        # Approval creates the catalogue product and records the reviewer's price in the same step.
        CheckConstraint(
            f"status NOT IN ({', '.join(repr(v) for v in STAGED_APPROVED_STATES)}) "
            "OR (product_id IS NOT NULL AND approved_price IS NOT NULL AND stock_known)",
            name="approved_states_need_product",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_product_id: Mapped[str | None] = mapped_column(Text)
    source_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    latest_source_hash: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    normalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingestion_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion_jobs.id", ondelete="SET NULL"))
    source_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    source_currency: Mapped[str | None] = mapped_column(CHAR(3))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending_review")
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    product: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    missing_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    stock_known: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    approved_price: Mapped[int | None] = mapped_column(Integer)
    approved_stock: Mapped[int | None] = mapped_column(Integer)
    # RESTRICT: a catalogue product that came from a review is never hard-deleted (products are archived).
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # Read-only view of the append-only trail; rows are written through StagedProductAudit only.
    audit: Mapped[list["StagedProductAudit"]] = relationship(
        "StagedProductAudit", order_by="StagedProductAudit.seq", lazy="selectin", viewonly=True
    )


Index("ix_staged_products_review_feed", StagedProduct.status, StagedProduct.created_at.desc(), StagedProduct.id.desc())
Index("ix_staged_products_product_id", StagedProduct.product_id, postgresql_where=text("product_id IS NOT NULL"))
Index("ix_staged_products_ingestion_job_id", StagedProduct.ingestion_job_id,
      postgresql_where=text("ingestion_job_id IS NOT NULL"))


class StagedProductAudit(Base):
    """Append-only review trail. A database trigger rejects UPDATE and DELETE (see migration 0004)."""
    __tablename__ = "staged_product_audit"
    __table_args__ = (
        CheckConstraint(_in("from_status", STAGED_STATUSES), name="from_status"),
        CheckConstraint(_in("to_status", STAGED_STATUSES), name="to_status"),
        CheckConstraint("char_length(action) >= 1", name="action_present"),
        Index("ix_staged_product_audit_staged_product_id_seq", "staged_product_id", "seq"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Strict chronological order: timestamps tie inside one transaction (now() is constant there).
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)
    # RESTRICT: staged products are archived, never deleted, so their trail cannot disappear.
    staged_product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staged_products.id", ondelete="RESTRICT"), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text, nullable=False, server_default="admin")
    note: Mapped[str | None] = mapped_column(Text)


class EnrichmentSuggestion(Base):
    """Reviewable, non-authoritative model suggestions for one staged product. Never read by the catalogue."""
    __tablename__ = "enrichment_suggestions"
    __table_args__ = (
        UniqueConstraint("staged_product_id", "input_content_hash", "prompt_version", "model",
                         name="uq_enrichment_suggestions_idempotency"),
        CheckConstraint(_in("status", ENRICHMENT_STATUSES), name="status"),
        CheckConstraint("attempts BETWEEN 0 AND 2", name="attempts_bounded"),
        Index("ix_enrichment_suggestions_active", "staged_product_id", unique=True,
              postgresql_where=text("status IN ('queued', 'running')")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    staged_product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staged_products.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    suggestions: Mapped[dict | None] = mapped_column(JSONB)
    validation_errors: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    vocabulary_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# --------------------------------------------------------------------------------------------
# Embeddings (S4b): derived, rebuildable vectors. Nothing here is catalogue truth and nothing reads back into it.
# --------------------------------------------------------------------------------------------
EMBEDDING_DIMENSIONS = 768  # the column width; a different width needs a new column and index (new migration)
EMBEDDING_STATUSES = ("queued", "running", "succeeded", "failed", "stale")
HNSW_M, HNSW_EF_CONSTRUCTION = 16, 64
EMBEDDING_KEY = ("source_revision", "representation_version", "representation_hash", "provider", "model",
                 "model_revision", "index_version")


class _EmbeddingColumns:
    """Shared by both tables. status: queued -> running -> succeeded | failed | stale (the source moved on)."""
    id: Mapped[uuid.UUID] = _uuid_pk()
    source_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    representation_version: Mapped[str] = mapped_column(Text, nullable=False)
    representation_hash: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    model_revision: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False, server_default=str(EMBEDDING_DIMENSIONS))
    index_version: Mapped[str] = mapped_column(Text, nullable=False)
    distance_metric: Mapped[str] = mapped_column(Text, nullable=False, server_default="cosine")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(Text)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_retryable: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def _embedding_table_args(table: str, owner: str) -> tuple:
    return (
        UniqueConstraint(owner, *EMBEDDING_KEY, name=f"uq_{table}_identity"),
        CheckConstraint(_in("status", EMBEDDING_STATUSES), name="status"),
        CheckConstraint(f"dimensions = {EMBEDDING_DIMENSIONS}", name="dimensions"),
        CheckConstraint("distance_metric = 'cosine'", name="distance_metric"),
        CheckConstraint("source_revision >= 1", name="source_revision_positive"),
        CheckConstraint("attempts >= 0 AND max_attempts >= 1 AND attempts <= max_attempts", name="attempts_bounded"),
        CheckConstraint("status <> 'succeeded' OR embedding IS NOT NULL", name="succeeded_has_vector"),
        CheckConstraint("status <> 'running' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
                        name="lease_present_while_running"),
        Index(f"ix_{table}_embedding_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": HNSW_M, "ef_construction": HNSW_EF_CONSTRUCTION},
              postgresql_ops={"embedding": "vector_cosine_ops"}, postgresql_where=text("status = 'succeeded'")),
        Index(f"ix_{table}_claimable", "available_at", postgresql_where=text("status = 'queued'")),
    )


class ProductEmbedding(_EmbeddingColumns, Base):
    __tablename__ = "product_embeddings"
    __table_args__ = (*_embedding_table_args("product_embeddings", "product_id"),
                      Index("ix_product_embeddings_product_id", "product_id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)


class VariantEmbedding(_EmbeddingColumns, Base):
    __tablename__ = "variant_embeddings"
    __table_args__ = (
        *_embedding_table_args("variant_embeddings", "variant_id"),
        # product_id is the variant's own product (composite FK), so a vector can never point at another product's variant.
        ForeignKeyConstraint(["variant_id", "product_id"], ["variants.id", "variants.product_id"], ondelete="CASCADE",
                             name="fk_variant_embeddings_variant_id_variants"),
        Index("ix_variant_embeddings_product_id", "product_id"),
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
