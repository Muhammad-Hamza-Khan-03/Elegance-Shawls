"""product_embeddings, variant_embeddings: derived pgvector rows with HNSW (cosine) indexes (additive)

Revision ID: 0009
Revises: 0008

Vectors are rebuildable and never catalogue truth. Old rows are kept; readers select the active version by predicate.
The HNSW indexes are partial (status = 'succeeded') with explicit m / ef_construction. They are built here inside the
migration transaction, which is only safe because the tables are new and empty. To (re)build one on a populated table
run it by hand, outside Alembic, so reads and writes are not blocked:
    CREATE INDEX CONCURRENTLY ix_product_embeddings_embedding_hnsw ON product_embeddings USING hnsw
      (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64) WHERE status = 'succeeded';
Downgrade drops only these two tables; the shared vector extension (created by 0001) stays installed.
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

NOW = sa.text("now()")
DIMENSIONS = 768
STATUSES = ("queued", "running", "succeeded", "failed", "stale")
KEY = ("source_revision", "representation_version", "representation_hash", "provider", "model", "model_revision",
       "index_version")


def _table(table: str, owner: str) -> None:
    columns = [sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False)]
    constraints = []
    if owner == "product_id":
        columns.append(sa.Column("product_id", pg.UUID(as_uuid=True), nullable=False))
        constraints.append(sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE",
                                                   name=f"fk_{table}_product_id_products"))
    else:
        columns += [sa.Column("variant_id", pg.UUID(as_uuid=True), nullable=False),
                    sa.Column("product_id", pg.UUID(as_uuid=True), nullable=False)]
        constraints += [
            sa.ForeignKeyConstraint(["variant_id", "product_id"], ["variants.id", "variants.product_id"],
                                    ondelete="CASCADE", name="fk_variant_embeddings_variant_id_variants"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE",
                                    name=f"fk_{table}_product_id_products")]
    op.create_table(
        table, *columns,
        sa.Column("source_revision", sa.Integer, nullable=False),
        sa.Column("representation_version", sa.Text, nullable=False),
        sa.Column("representation_hash", sa.Text, nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("model_revision", sa.Text, server_default="", nullable=False),
        sa.Column("dimensions", sa.Integer, server_default=str(DIMENSIONS), nullable=False),
        sa.Column("index_version", sa.Text, nullable=False),
        sa.Column("distance_metric", sa.Text, server_default="cosine", nullable=False),
        sa.Column("embedding", Vector(DIMENSIONS)),
        sa.Column("status", sa.Text, server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer, server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer, server_default="3", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("lease_owner", sa.Text),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("last_error_retryable", sa.Boolean),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name=f"pk_{table}"),
        *constraints,
        sa.UniqueConstraint(owner, *KEY, name=f"uq_{table}_identity"),
        sa.CheckConstraint(f"status IN ({', '.join(repr(v) for v in STATUSES)})", name=op.f(f"ck_{table}_status")),
        sa.CheckConstraint(f"dimensions = {DIMENSIONS}", name=op.f(f"ck_{table}_dimensions")),
        sa.CheckConstraint("distance_metric = 'cosine'", name=op.f(f"ck_{table}_distance_metric")),
        sa.CheckConstraint("source_revision >= 1", name=op.f(f"ck_{table}_source_revision_positive")),
        sa.CheckConstraint("attempts >= 0 AND max_attempts >= 1 AND attempts <= max_attempts",
                           name=op.f(f"ck_{table}_attempts_bounded")),
        sa.CheckConstraint("status <> 'succeeded' OR embedding IS NOT NULL", name=op.f(f"ck_{table}_succeeded_has_vector")),
        sa.CheckConstraint("status <> 'running' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
                           name=op.f(f"ck_{table}_lease_present_while_running")),
    )
    op.create_index(f"ix_{table}_product_id", table, ["product_id"])
    op.create_index(f"ix_{table}_claimable", table, ["available_at"], postgresql_where=sa.text("status = 'queued'"))
    op.create_index(f"ix_{table}_embedding_hnsw", table, ["embedding"], postgresql_using="hnsw",
                    postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"embedding": "vector_cosine_ops"},
                    postgresql_where=sa.text("status = 'succeeded'"))


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    if op.get_bind().execute(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar() is None:
        raise RuntimeError("the pgvector extension is not installed; an administrator must run CREATE EXTENSION vector")
    _table("product_embeddings", "product_id")
    _table("variant_embeddings", "variant_id")


def downgrade() -> None:
    op.drop_table("variant_embeddings")
    op.drop_table("product_embeddings")
