"""catalogue: products and variants

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slug", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("category", sa.Text, server_default="shawls", nullable=False),
        sa.Column("status", sa.Text, server_default="draft", nullable=False),
        sa.Column("is_active", sa.Boolean, sa.Computed("status = 'active'", persisted=True), nullable=False),
        sa.Column("cover_image_url", sa.Text, nullable=False),
        sa.Column("images", sa.ARRAY(sa.Text), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("main_description", sa.Text),
        sa.Column("price", sa.Integer, nullable=False),
        sa.Column("currency", sa.CHAR(3), server_default="PKR", nullable=False),
        sa.Column("material", sa.Text),
        sa.Column("sizing", sa.Text),
        sa.Column("weight", sa.Text),
        sa.Column("item_number", sa.Text),
        sa.Column("revision", sa.Integer, server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("slug", name="uq_products_slug"),
        sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND char_length(slug) <= 180", name=op.f("ck_products_slug_format")),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 160", name=op.f("ck_products_name_length")),
        sa.CheckConstraint(_in("category", ("shawls", "stoles", "scarves")), name=op.f("ck_products_category")),
        sa.CheckConstraint(_in("status", ("active", "draft", "out_of_stock", "archived")), name=op.f("ck_products_status")),
        sa.CheckConstraint("cardinality(images) <= 12", name=op.f("ck_products_images_max")),
        sa.CheckConstraint("char_length(main_description) <= 5000", name=op.f("ck_products_description_length")),
        sa.CheckConstraint("char_length(material) <= 200 AND char_length(sizing) <= 200",
                           name=op.f("ck_products_material_sizing_length")),
        sa.CheckConstraint("char_length(weight) <= 100 AND char_length(item_number) <= 100",
                           name=op.f("ck_products_weight_item_length")),
        sa.CheckConstraint("price >= 0", name=op.f("ck_products_price_nonnegative")),
        sa.CheckConstraint("currency = upper(currency)", name=op.f("ck_products_currency_upper")),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_products_revision_positive")),
    )
    op.create_index("ix_products_public_feed", "products", [sa.text("created_at DESC"), sa.text("id DESC")],
                    postgresql_where=sa.text("status = 'active'"))
    op.create_index("ix_products_created_at_id", "products", [sa.text("created_at DESC"), sa.text("id DESC")])
    op.create_index("ix_products_item_number", "products", ["item_number"],
                    postgresql_where=sa.text("item_number IS NOT NULL"))

    op.create_table(
        "variants",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("product_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("color", sa.Text),
        sa.Column("size", sa.Text, server_default="Free Size", nullable=False),
        sa.Column("image_url", sa.Text, nullable=False),
        sa.Column("price", sa.Integer, nullable=False),
        sa.Column("currency", sa.CHAR(3), server_default="PKR", nullable=False),
        sa.Column("stock", sa.Integer, server_default="0", nullable=False),
        sa.Column("stock_status", sa.Text,
                  sa.Computed("CASE WHEN stock > 0 THEN 'In stock' ELSE 'Out of stock' END", persisted=True),
                  nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_variants"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE",
                                name="fk_variants_product_id_products"),
        sa.UniqueConstraint("product_id", "position", name="uq_variants_product_id_position",
                            deferrable=True, initially="DEFERRED"),
        sa.CheckConstraint("position >= 0", name=op.f("ck_variants_position_nonnegative")),
        sa.CheckConstraint("char_length(name) >= 1", name=op.f("ck_variants_name_present")),
        sa.CheckConstraint("char_length(color) >= 1", name=op.f("ck_variants_color_not_empty")),
        sa.CheckConstraint("price >= 0", name=op.f("ck_variants_price_nonnegative")),
        sa.CheckConstraint("stock >= 0", name=op.f("ck_variants_stock_nonnegative")),
        sa.CheckConstraint("currency = upper(currency)", name=op.f("ck_variants_currency_upper")),
    )


def downgrade() -> None:
    op.drop_table("variants")
    op.drop_table("products")
