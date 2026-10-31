"""durable, non-sensitive enquiry references for the WhatsApp handoff

Revision ID: 0011
Revises: 0010

Additive only: one new table. It holds a short public reference and a cart snapshot (product/variant ids,
names, quantities, unit prices). No customer name, phone, address or session identifier is stored; it is
not an order, reservation or message.

Rollback: downgrade drops `enquiries`, which destroys every reference issued since the upgrade (customers may
still quote them on WhatsApp). It therefore REFUSES to run while rows exist unless
ALEMBIC_ALLOW_ENQUIRY_DATA_LOSS=1 is set (take a pg_dump first).
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
        "enquiries",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("reference", sa.Text, nullable=False),
        sa.Column("items", pg.JSONB, nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("total", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_enquiries"),
        sa.UniqueConstraint("reference", name="uq_enquiries_reference"),
        sa.CheckConstraint("reference ~ '^ES-[A-Z0-9]{6,12}$'", name=op.f("ck_enquiries_reference_format")),
        sa.CheckConstraint("currency = upper(currency)", name=op.f("ck_enquiries_currency_upper")),
        sa.CheckConstraint("total >= 0", name=op.f("ck_enquiries_total_nonnegative")),
        sa.CheckConstraint("jsonb_typeof(items) = 'array' AND jsonb_array_length(items) BETWEEN 1 AND 50",
                           name=op.f("ck_enquiries_items_array")),
    )
    op.create_index("ix_enquiries_created_at", "enquiries", [sa.text("created_at DESC"), sa.text("id DESC")])


def downgrade() -> None:
    at_risk = op.get_bind().execute(sa.text("SELECT count(*) FROM enquiries")).scalar()
    if at_risk and os.environ.get("ALEMBIC_ALLOW_ENQUIRY_DATA_LOSS") != "1":
        raise RuntimeError(
            f"Refusing to downgrade 0008: {at_risk} enquiry references would be lost. "
            "Back up with pg_dump, then rerun with ALEMBIC_ALLOW_ENQUIRY_DATA_LOSS=1."
        )
    op.drop_index("ix_enquiries_created_at", table_name="enquiries")
    op.drop_table("enquiries")
