"""individual admin accounts, server-side sessions and an append-only audit trail

Revision ID: 0010
Revises: 0009

Additive only: two new tables and two NULL-safe columns on audit_log (existing rows read as outcome
'success', detail NULL). Nothing is rewritten or dropped on upgrade.

Rollback: downgrade removes the new tables and columns, which destroys admin accounts, sessions and
audit outcomes/details recorded since the upgrade. It therefore REFUSES to run when any such data
exists unless ALEMBIC_ALLOW_ADMIN_DATA_LOSS=1 is set (take a pg_dump first). Audit rows keep action,
target and actor_id (the account UUID) across a rollback.
"""
import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "admin_accounts",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("status", sa.Text, server_default="active", nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("failed_login_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", pg.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_admin_accounts"),
        sa.UniqueConstraint("email", name="uq_admin_accounts_email"),
        sa.ForeignKeyConstraint(["created_by"], ["admin_accounts.id"], name="fk_admin_accounts_created_by_admin_accounts"),
        sa.CheckConstraint(_in("role", ("viewer", "editor", "owner")), name=op.f("ck_admin_accounts_role")),
        sa.CheckConstraint(_in("status", ("active", "disabled")), name=op.f("ck_admin_accounts_status")),
        sa.CheckConstraint("email = lower(email) AND char_length(email) BETWEEN 3 AND 254",
                           name=op.f("ck_admin_accounts_email_format")),
        sa.CheckConstraint("failed_login_count >= 0", name=op.f("ck_admin_accounts_failed_logins_nonnegative")),
    )
    op.create_table(
        "admin_sessions",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_reason", sa.Text),
        sa.PrimaryKeyConstraint("id", name="pk_admin_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_admin_sessions_token_hash"),
        sa.ForeignKeyConstraint(["account_id"], ["admin_accounts.id"], ondelete="CASCADE",
                                name="fk_admin_sessions_account_id_admin_accounts"),
        sa.CheckConstraint("expires_at > created_at", name=op.f("ck_admin_sessions_expiry_after_creation")),
    )
    op.create_index("ix_admin_sessions_account_id_live", "admin_sessions", ["account_id"],
                    postgresql_where=sa.text("revoked_at IS NULL"))

    op.add_column("audit_log", sa.Column("outcome", sa.Text, server_default="success", nullable=False))
    op.add_column("audit_log", sa.Column("detail", pg.JSONB))
    op.create_check_constraint(op.f("ck_audit_log_outcome"), "audit_log",
                               _in("outcome", ("accepted", "success", "failure", "denied")))

    # Append-only except for one transition: an 'accepted' row may be finalised to success/failure (detail
    # may grow). Rows are never deleted and identity columns never change.
    op.execute("""
        CREATE FUNCTION audit_log_guard() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'audit_log is append-only (DELETE not allowed)' USING ERRCODE = 'restrict_violation';
            END IF;
            IF OLD.outcome = 'accepted' AND NEW.outcome IN ('success', 'failure')
               AND (OLD.id, OLD.actor_type, OLD.actor_id, OLD.action, OLD.target, OLD.created_at)
                   IS NOT DISTINCT FROM (NEW.id, NEW.actor_type, NEW.actor_id, NEW.action, NEW.target, NEW.created_at) THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'audit_log is append-only (UPDATE not allowed)' USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("CREATE TRIGGER audit_log_guard BEFORE UPDATE OR DELETE ON audit_log "
               "FOR EACH ROW EXECUTE FUNCTION audit_log_guard()")


def downgrade() -> None:
    bind = op.get_bind()
    at_risk = bind.execute(sa.text(
        "SELECT (SELECT count(*) FROM admin_accounts) + (SELECT count(*) FROM admin_sessions)"
        " + (SELECT count(*) FROM audit_log WHERE outcome <> 'success' OR detail IS NOT NULL)")).scalar()
    if at_risk and os.environ.get("ALEMBIC_ALLOW_ADMIN_DATA_LOSS") != "1":
        raise RuntimeError(
            f"Refusing to downgrade 0007: {at_risk} admin account/session/audit-detail rows would be lost. "
            "Back up with pg_dump, then rerun with ALEMBIC_ALLOW_ADMIN_DATA_LOSS=1."
        )
    op.execute("DROP TRIGGER IF EXISTS audit_log_guard ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_guard()")
    op.drop_constraint(op.f("ck_audit_log_outcome"), "audit_log", type_="check")
    op.drop_column("audit_log", "detail")
    op.drop_column("audit_log", "outcome")
    op.drop_table("admin_sessions")
    op.drop_table("admin_accounts")
