"""pgvector persistence for product embeddings and their backfill queue (M2-S2)

Revision ID: 0012
Revises: 0011

Additive only: two new tables, no change to existing ones, no public route reads them. `semantic_embeddings`
holds one vector per (product, provider, model, representation version) with the content hash and product
revision it was computed from. `semantic_embedding_jobs` is the lease/retry/cancel queue the backfill worker drains.
No ANN index yet (nothing queries by similarity; added with the search slice). The `vector` extension was
created by 0001 and is shared, so it is left installed.

Rollback: downgrade drops both tables. Embeddings are derived data and are rebuilt by the backfill, so no
data-loss guard is needed.
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def _pk_and_product():
    return [
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("product_id", pg.UUID(as_uuid=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "semantic_embeddings",
        *_pk_and_product(),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("dimensions", sa.Integer, nullable=False),
        sa.Column("representation_version", sa.Text, nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.Column("product_revision", sa.Integer, nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_semantic_embeddings"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE",
                                name="fk_semantic_embeddings_product_id_products"),
        sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_semantic_embeddings_content_hash_format")),
        sa.CheckConstraint("product_revision >= 1", name=op.f("ck_semantic_embeddings_revision_positive")),
        sa.CheckConstraint("dimensions >= 1 AND vector_dims(embedding) = dimensions",
                           name=op.f("ck_semantic_embeddings_dimensions_match")),
    )
    op.create_index("ix_semantic_embeddings_target", "semantic_embeddings",
                    ["product_id", "provider", "model", "representation_version"], unique=True)

    op.create_table(
        "semantic_embedding_jobs",
        *_pk_and_product(),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("representation_version", sa.Text, nullable=False),
        sa.Column("status", sa.Text, server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer, server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer, server_default="3", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("lease_owner", sa.Text),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("last_error", sa.Text),
        sa.Column("result", pg.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_semantic_embedding_jobs"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE",
                                name="fk_semantic_embedding_jobs_product_id_products"),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'retrying', 'failed', 'cancelled')",
                           name=op.f("ck_semantic_embedding_jobs_status")),
        sa.CheckConstraint("attempts >= 0 AND max_attempts >= 1 AND attempts <= max_attempts",
                           name=op.f("ck_semantic_embedding_jobs_attempts_bounded")),
        sa.CheckConstraint("status <> 'running' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
                           name=op.f("ck_semantic_embedding_jobs_lease_present_while_running")),
    )
    op.create_index("ix_semantic_embedding_jobs_target", "semantic_embedding_jobs",
                    ["product_id", "provider", "model", "representation_version"], unique=True)
    op.create_index("ix_semantic_embedding_jobs_claimable", "semantic_embedding_jobs", ["available_at"],
                    postgresql_where=sa.text("status IN ('queued', 'retrying') AND NOT cancel_requested"))
    op.create_index("ix_semantic_embedding_jobs_running_lease", "semantic_embedding_jobs", ["lease_expires_at"],
                    postgresql_where=sa.text("status = 'running'"))


def downgrade() -> None:
    op.drop_table("semantic_embedding_jobs")        # indexes go with the tables
    op.drop_table("semantic_embeddings")
