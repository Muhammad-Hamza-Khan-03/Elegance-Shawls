"""Add the monotonic customer memory privacy epoch (M4 Batch C readiness).

The epoch is bumped by destructive memory operations. Queued extraction work must
capture and re-check it before writing. This migration contains no data and does
not enable extraction.
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("memory_version", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.create_check_constraint("ck_customers_memory_version_nonnegative", "customers", "memory_version >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_customers_memory_version_nonnegative", "customers", type_="check")
    op.drop_column("customers", "memory_version")
