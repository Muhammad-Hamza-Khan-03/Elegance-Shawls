"""customer sessions: server-side opaque sessions for authenticated customers (M4)

Revision ID: 0015
Revises: 0014

Additive only: one new table, nothing existing is changed. Only the SHA-256 of the opaque session token is stored (never the token
or any identity-provider credential). Rows cascade from `customers`. Like admin_sessions the table has no row-level security: the
application role reaches it through the verifier and the customer-auth routes only. No data is seeded.

Rollback: downgrade drops the table, which only signs every customer out; customers and identities are untouched.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_sessions",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("customer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_reason", sa.Text),
        sa.PrimaryKeyConstraint("id", name="pk_customer_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_customer_sessions_token_hash"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE", name="fk_customer_sessions_customer_id_customers"),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_customer_sessions_token_hash_format")),
        sa.CheckConstraint("expires_at > created_at", name=op.f("ck_customer_sessions_expiry_after_creation")),
    )
    op.create_index("ix_customer_sessions_customer_id_live", "customer_sessions", ["customer_id"],
                    postgresql_where=sa.text("revoked_at IS NULL"))


def downgrade() -> None:
    op.drop_table("customer_sessions")
