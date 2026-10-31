"""enrichment_suggestions: reviewable model suggestions for staged products (additive)

Revision ID: 0008
Revises: 0007

Suggestions are advisory artifacts: nothing here references the catalogue. One active (queued/running)
suggestion per staged product; the idempotency key makes a repeated request return the existing row.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

NOW = sa.text("now()")
STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")


def upgrade() -> None:
    op.create_table(
        "enrichment_suggestions",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("staged_product_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text, server_default="queued", nullable=False),
        sa.Column("suggestions", pg.JSONB),
        sa.Column("validation_errors", pg.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("prompt_version", sa.Text, nullable=False),
        sa.Column("vocabulary_version", sa.Text, nullable=False),
        sa.Column("input_content_hash", sa.Text, nullable=False),
        sa.Column("attempts", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text),
        sa.Column("trace_id", sa.Text),
        sa.Column("reviewed_by", sa.Text),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_enrichment_suggestions"),
        sa.ForeignKeyConstraint(["staged_product_id"], ["staged_products.id"],
                                name="fk_enrichment_suggestions_staged_product_id_staged_products", ondelete="RESTRICT"),
        sa.UniqueConstraint("staged_product_id", "input_content_hash", "prompt_version", "model",
                            name="uq_enrichment_suggestions_idempotency"),
        sa.CheckConstraint(f"status IN ({', '.join(repr(v) for v in STATUSES)})", name=op.f("ck_enrichment_suggestions_status")),
        sa.CheckConstraint("attempts BETWEEN 0 AND 2", name=op.f("ck_enrichment_suggestions_attempts_bounded")),
    )
    op.create_index("ix_enrichment_suggestions_active", "enrichment_suggestions", ["staged_product_id"], unique=True,
                    postgresql_where=sa.text("status IN ('queued', 'running')"))


def downgrade() -> None:
    op.drop_table("enrichment_suggestions")
