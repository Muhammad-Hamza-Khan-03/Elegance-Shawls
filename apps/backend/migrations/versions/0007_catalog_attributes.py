"""catalog_attributes: normalised product/variant attributes with provenance

Revision ID: 0007
Revises: 0006

variant_id NULL = a product-level attribute; value NULL = explicitly unknown. A variant attribute must
belong to its own product (composite FK). Downgrade drops only what this revision created.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

NOW = sa.text("now()")
KEYS = ("color_name", "color_family", "fabric", "composition", "pattern", "occasion", "season", "style", "authenticity")
SOURCES = ("visual_suggestion", "supplier_declared", "staff_approved", "imported")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_unique_constraint("uq_variants_id_product_id", "variants", ["id", "product_id"])
    op.create_table(
        "catalog_attributes",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("product_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", pg.UUID(as_uuid=True)),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("value", sa.Text),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("model_version", sa.Text),
        sa.Column("approved_by", sa.Text),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_catalog_attributes"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_catalog_attributes_product_id_products", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id", "product_id"], ["variants.id", "variants.product_id"],
                                name="fk_catalog_attributes_variant_id_variants", ondelete="CASCADE"),
        sa.CheckConstraint(_in("key", KEYS), name=op.f("ck_catalog_attributes_key")),
        sa.CheckConstraint(_in("source", SOURCES), name=op.f("ck_catalog_attributes_source")),
        sa.CheckConstraint("char_length(value) BETWEEN 1 AND 200", name=op.f("ck_catalog_attributes_value_length")),
        sa.CheckConstraint("char_length(model_version) BETWEEN 1 AND 100 AND char_length(approved_by) BETWEEN 1 AND 200",
                           name=op.f("ck_catalog_attributes_provenance_length")),
        sa.CheckConstraint(
            "(source = 'staff_approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL) "
            "OR (source <> 'staff_approved' AND approved_by IS NULL AND approved_at IS NULL)",
            name=op.f("ck_catalog_attributes_approval")),
    )
    op.create_index("ix_catalog_attributes_product_key", "catalog_attributes", ["product_id", "key"], unique=True,
                    postgresql_where=sa.text("variant_id IS NULL"))
    op.create_index("ix_catalog_attributes_variant_key", "catalog_attributes", ["variant_id", "key"], unique=True,
                    postgresql_where=sa.text("variant_id IS NOT NULL"))
    op.create_index("ix_catalog_attributes_product_id", "catalog_attributes", ["product_id"])


def downgrade() -> None:
    op.drop_table("catalog_attributes")
    op.drop_constraint("uq_variants_id_product_id", "variants", type_="unique")
