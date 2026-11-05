"""action_executions: durable replay protection for confirmed assistant actions (additive)

Revision ID: 0010
Revises: 0009

One row per (session_id, action_id); the fingerprint binds the row to the exact validated params. Stores only the inert
execution intent (opaque ids and quantities), never prices, messages or personal data.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_executions",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", sa.Text, nullable=False),
        sa.Column("action_id", sa.Text, nullable=False),
        sa.Column("fingerprint", sa.CHAR(64), nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("result", pg.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_action_executions"),
        sa.UniqueConstraint("session_id", "action_id", name="uq_action_executions_session_id_action_id"),
        sa.CheckConstraint("action IN ('add_to_cart', 'start_whatsapp_order')", name="action"),
    )
    op.create_index("ix_action_executions_created_at", "action_executions", ["created_at"])


def downgrade() -> None:
    op.drop_table("action_executions")
