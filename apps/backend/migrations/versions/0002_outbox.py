"""outbox: durable change records for the embedding worker

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("aggregate", sa.Text, nullable=False),
        sa.Column("aggregate_id", sa.CHAR(24), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer, server_default="0", nullable=False),
        sa.Column("last_error", sa.Text),
        sa.PrimaryKeyConstraint("id", name="pk_outbox"),
        sa.CheckConstraint("aggregate IN ('product', 'variant')", name=op.f("ck_outbox_aggregate")),
        sa.CheckConstraint("event_type IN ('created', 'updated', 'archived')", name=op.f("ck_outbox_event_type")),
        sa.CheckConstraint("aggregate_id ~ '^[0-9a-f]{24}$'", name=op.f("ck_outbox_aggregate_id_format")),
        sa.CheckConstraint("revision >= 0", name=op.f("ck_outbox_revision_nonnegative")),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_outbox_attempts_nonnegative")),
        sa.UniqueConstraint("aggregate", "aggregate_id", "revision", "event_type",
                            name="uq_outbox_aggregate_aggregate_id_revision_event_type"),
    )
    op.create_index("ix_outbox_unprocessed", "outbox", ["created_at"], postgresql_where=sa.text("processed_at IS NULL"))


def downgrade() -> None:
    op.drop_table("outbox")
