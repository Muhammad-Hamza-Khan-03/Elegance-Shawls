"""outbox: aggregate_id becomes a UUID (products and variants now have UUID identifiers)

Revision ID: 0005
Revises: 0004

The outbox is empty until the catalogue runs on PostgreSQL. The USING casts are only evaluated for
existing rows, so a populated table fails loudly instead of being silently rewritten.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_outbox_aggregate_id_format"), "outbox", type_="check")
    op.alter_column("outbox", "aggregate_id", type_=pg.UUID(as_uuid=True), existing_nullable=False,
                    postgresql_using="aggregate_id::uuid")


def downgrade() -> None:
    op.alter_column("outbox", "aggregate_id", type_=sa.CHAR(24), existing_nullable=False,
                    postgresql_using="aggregate_id::text")
    op.create_check_constraint(op.f("ck_outbox_aggregate_id_format"), "outbox", "aggregate_id ~ '^[0-9a-f]{24}$'")
