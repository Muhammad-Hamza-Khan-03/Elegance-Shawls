"""Bounded M4 Batch A event merge ledger and optional exchange replay guard.

No existing customer or identity is rewritten. Downgrade refuses while merge evidence exists.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customer_sessions", sa.Column("exchange_hash", sa.CHAR(64), nullable=True))
    op.create_unique_constraint("uq_customer_sessions_exchange_hash", "customer_sessions", ["exchange_hash"])
    op.create_check_constraint("ck_customer_sessions_exchange_hash_format", "customer_sessions",
                               "exchange_hash IS NULL OR exchange_hash ~ '^[0-9a-f]{64}$'")
    op.create_table(
        "anonymous_merges",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_hash", sa.CHAR(64), nullable=False),
        sa.Column("customer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("merged_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_anonymous_merges"),
        sa.UniqueConstraint("session_hash", name="uq_anonymous_merges_session_hash"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE", name="fk_anonymous_merges_customer_id_customers"),
        sa.CheckConstraint("session_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_anonymous_merges_session_hash_format")),
        sa.CheckConstraint("merged_count BETWEEN 1 AND 100", name=op.f("ck_anonymous_merges_merged_count_bounds")),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM anonymous_merges")).scalar():
        raise RuntimeError("Refusing to remove anonymous merge evidence; restore a backup for rollback")
    op.drop_table("anonymous_merges")
    op.drop_constraint("ck_customer_sessions_exchange_hash_format", "customer_sessions", type_="check")
    op.drop_constraint("uq_customer_sessions_exchange_hash", "customer_sessions", type_="unique")
    op.drop_column("customer_sessions", "exchange_hash")
