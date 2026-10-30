"""explicit customer memory: per-customer consent and user-scoped memory items (M4-S1)

Revision ID: 0011
Revises: 0010

Additive only: two new tables, no change to existing ones. `memory_consents` has one row per customer who ever chose; no row
means no consent (memory is off by default). `memory_items` holds only what a customer explicitly asked to be remembered, with
provenance (`source`, `source_ref`), a `reason` and a retention window (`expires_at`). Deleting scrubs the content columns in
place and keeps a content-free tombstone, which is what makes a replayed create unable to resurrect a deleted memory. Both tables
cascade from `customers`. No customer data is seeded.

Rollback: downgrade drops both tables, which erases every customer's consent and memories. It therefore REFUSES to run while
rows exist unless ALEMBIC_ALLOW_MEMORY_DATA_LOSS=1 is set (take a pg_dump first).
"""
import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_consents",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("customer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("granted", sa.Boolean, nullable=False),
        sa.Column("policy_version", sa.Text, nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_memory_consents"),
        sa.UniqueConstraint("customer_id", name="uq_memory_consents_customer_id"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_memory_consents_customer_id_customers", ondelete="CASCADE"),
        sa.CheckConstraint("char_length(policy_version) BETWEEN 1 AND 32", name=op.f("ck_memory_consents_policy_version")),
    )
    op.create_table(
        "memory_items",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("customer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("status", sa.Text, server_default="active", nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("key", sa.Text, nullable=True),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("source_ref", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("fingerprint", sa.CHAR(64), nullable=True),
        sa.Column("version", sa.Integer, server_default=sa.text("1"), nullable=False),
        sa.Column("retention_days", sa.Integer, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_memory_items"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_memory_items_customer_id_customers", ondelete="CASCADE"),
        sa.UniqueConstraint("customer_id", "idempotency_key", name="uq_memory_items_customer_id_idempotency_key"),
        sa.CheckConstraint("category IN ('preference', 'session_constraint', 'purchase_context')", name=op.f("ck_memory_items_category")),
        sa.CheckConstraint("source IN ('user_explicit', 'memory_page')", name=op.f("ck_memory_items_source")),
        sa.CheckConstraint("status IN ('active', 'deleted')", name=op.f("ck_memory_items_status")),
        sa.CheckConstraint("idempotency_key ~ '^idem_[A-Za-z0-9_-]{16,64}$'", name=op.f("ck_memory_items_idempotency_key_format")),
        sa.CheckConstraint("retention_days BETWEEN 1 AND 365 AND version >= 1", name=op.f("ck_memory_items_bounds")),
        sa.CheckConstraint("expires_at > created_at", name=op.f("ck_memory_items_expiry_after_creation")),
        sa.CheckConstraint("status <> 'active' OR (key ~ '^[a-z][a-z0-9_]{0,63}$' AND char_length(value) BETWEEN 1 AND 200 "
                           "AND (reason IS NULL OR char_length(reason) BETWEEN 1 AND 200) AND fingerprint ~ '^[0-9a-f]{64}$')",
                           name=op.f("ck_memory_items_active_content")),
        sa.CheckConstraint("status <> 'deleted' OR (key IS NULL AND value IS NULL AND reason IS NULL AND source_ref IS NULL "
                           "AND fingerprint IS NULL AND deleted_at IS NOT NULL)", name=op.f("ck_memory_items_deleted_is_scrubbed")),
    )
    op.create_index("ix_memory_items_customer_id_key_active", "memory_items", ["customer_id", "key"], unique=True,
                    postgresql_where=sa.text("status = 'active'"))
    op.create_index("ix_memory_items_customer_id_created_at", "memory_items", ["customer_id", "created_at", "id"])
    op.create_index("ix_memory_items_expires_at_active", "memory_items", ["expires_at"], postgresql_where=sa.text("status = 'active'"))
    op.create_index("ix_memory_items_deleted_at", "memory_items", ["deleted_at"], postgresql_where=sa.text("status = 'deleted'"))


def downgrade() -> None:
    bind = op.get_bind()
    at_risk = bind.execute(sa.text("SELECT (SELECT count(*) FROM memory_items) + (SELECT count(*) FROM memory_consents)")).scalar()
    if at_risk and os.environ.get("ALEMBIC_ALLOW_MEMORY_DATA_LOSS") != "1":
        raise RuntimeError(
            f"Refusing to downgrade 0011: {at_risk} customer memory/consent records would be lost. "
            "Back up with pg_dump, then rerun with ALEMBIC_ALLOW_MEMORY_DATA_LOSS=1."
        )
    op.drop_table("memory_items")
    op.drop_table("memory_consents")
