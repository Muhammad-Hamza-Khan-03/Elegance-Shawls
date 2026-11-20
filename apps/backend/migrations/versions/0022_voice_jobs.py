"""Voice job ledger for Phase 4 (issue #111), additive and unused until voice is enabled.

One row per voice request: status, bounded clip length and a reference to where the clip is held (never the audio itself).
The 30 second limit is a database constraint, not only an application check. `audio_ref` is cleared and `audio_deleted_at`
set by voice/retention.py, so the row survives as a metric while the audio does not.
Rollback: downgrade drops the table (no other table references it).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_jobs",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("audio_ref", sa.Text, nullable=True),
        sa.Column("audio_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_voice_jobs"),
        sa.CheckConstraint("status in ('queued','done','failed')", name=op.f("ck_voice_jobs_status")),
        sa.CheckConstraint("duration_ms between 1 and 30000", name=op.f("ck_voice_jobs_duration_ms")),
    )
    op.create_index("ix_voice_jobs_created_at", "voice_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_voice_jobs_created_at", table_name="voice_jobs")
    op.drop_table("voice_jobs")
