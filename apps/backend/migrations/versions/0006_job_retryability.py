"""ingestion_jobs.last_error_retryable: whether the last failure was classified retryable

Revision ID: 0006
Revises: 0005

The refresh summary uses this flag to split retryable from
non-retryable failures. NULL means "no failure recorded".
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_jobs", sa.Column("last_error_retryable", sa.Boolean))


def downgrade() -> None:
    op.drop_column("ingestion_jobs", "last_error_retryable")
