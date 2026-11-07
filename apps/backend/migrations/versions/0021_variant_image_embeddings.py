"""Image vectors for "find similar products from a customer's photo" (WhatsApp image matching, optional).

Additive: one table. One 512-dimension vector (CLIP ViT-B/32) per (variant, model) with the hash of the image bytes it was
computed from, so a changed image is re-embedded and an unchanged one is skipped. Derived data, rebuilt by
scripts/image_embedding_backfill.py. No ANN index yet: the catalogue is small enough for an exact scan; add HNSW when it is not.
Customer photos are never stored: only the catalogue's own images are embedded.
Rollback: downgrade drops the table (rebuildable).
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "variant_image_embeddings",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("variant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("image_hash", sa.Text, nullable=False),
        sa.Column("embedding", Vector(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_variant_image_embeddings"),
        sa.ForeignKeyConstraint(["variant_id"], ["variants.id"], ondelete="CASCADE", name="fk_variant_image_embeddings_variant_id_variants"),
        sa.UniqueConstraint("variant_id", "model", name="uq_variant_image_embeddings_variant_id_model"),
        sa.CheckConstraint("image_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_variant_image_embeddings_image_hash_format")),
    )


def downgrade() -> None:
    op.drop_table("variant_image_embeddings")
