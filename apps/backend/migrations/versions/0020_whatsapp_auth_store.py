"""WhatsApp bridge auth state in PostgreSQL (optional; WHATSAPP_AUTH_STORE=postgres). Its own least-privilege role can reach this table only.

Values are AES-256-GCM ciphertext written by the bridge with a key this database never sees, so dumps and the backup role read
only ciphertext. Role `elegance_wa_auth` is created by an operator (deploy/postgres/whatsapp-auth-role.sh); if it already exists
this migration grants it access. Downgrade drops the table: the linked device must then be paired again.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_auth_entries",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("key_id", sa.Text, nullable=False),
        sa.Column("value", sa.LargeBinary, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_whatsapp_auth_entries"),
        sa.UniqueConstraint("session", "kind", "key_id", name="uq_whatsapp_auth_entries_session_kind_key_id"),
    )
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elegance_wa_auth') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON whatsapp_auth_entries TO elegance_wa_auth;
          END IF;
        END $$""")


def downgrade() -> None:
    op.drop_table("whatsapp_auth_entries")
