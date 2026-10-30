"""durable idempotency and audit records for confirmed assistant actions (M3-S4)

Revision ID: 0010
Revises: 0009

Additive only: one new table, no change to existing ones. One row per (session, idempotency key) claims an execution
of add_to_cart or start_whatsapp_enquiry across all workers: `pending` (claimed, leased), `committed` (result stored in the
same transaction as the enquiry it created) or `failed` (retryable). It stores only the SHA-256 of the session id, the
fingerprint of the request, a fixed-shape audit record and the non-sensitive result already returned to the browser. No raw
session id, params, prices, customer details or exception text. It is not an order, message or reservation.

Rollback: downgrade drops `action_executions`, which erases replay protection and the audit trail for confirmed actions. It
therefore REFUSES to run while rows exist unless ALEMBIC_ALLOW_ACTION_EXECUTION_DATA_LOSS=1 is set (take a pg_dump first).
"""
import os

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
        sa.Column("session_hash", sa.CHAR(64), nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("action_type", sa.Text, nullable=False),
        sa.Column("fingerprint", sa.CHAR(64), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("attempt", sa.Integer, server_default=sa.text("1"), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", pg.JSONB, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("audit", pg.JSONB, nullable=False),
        sa.Column("replay_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_action_executions"),
        sa.UniqueConstraint("session_hash", "idempotency_key", name="uq_action_executions_session_hash_idempotency_key"),
        sa.CheckConstraint("action_type IN ('add_to_cart', 'start_whatsapp_enquiry')", name=op.f("ck_action_executions_action_type")),
        sa.CheckConstraint("status IN ('pending', 'committed', 'failed')", name=op.f("ck_action_executions_status")),
        sa.CheckConstraint("session_hash ~ '^[0-9a-f]{64}$' AND fingerprint ~ '^[0-9a-f]{64}$'", name=op.f("ck_action_executions_hash_format")),
        sa.CheckConstraint("attempt >= 1 AND replay_count >= 0", name=op.f("ck_action_executions_counters")),
        sa.CheckConstraint("(status = 'committed') = (result IS NOT NULL)", name=op.f("ck_action_executions_result_iff_committed")),
        sa.CheckConstraint("(status = 'failed') = (reason IS NOT NULL)", name=op.f("ck_action_executions_reason_iff_failed")),
        sa.CheckConstraint("jsonb_typeof(audit) = 'object'", name=op.f("ck_action_executions_audit_object")),
    )


def downgrade() -> None:
    at_risk = op.get_bind().execute(sa.text("SELECT count(*) FROM action_executions")).scalar()
    if at_risk and os.environ.get("ALEMBIC_ALLOW_ACTION_EXECUTION_DATA_LOSS") != "1":
        raise RuntimeError(
            f"Refusing to downgrade 0010: {at_risk} action execution records would be lost. "
            "Back up with pg_dump, then rerun with ALEMBIC_ALLOW_ACTION_EXECUTION_DATA_LOSS=1."
        )
    op.drop_table("action_executions")
