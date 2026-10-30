"""relational foundation: customers, identities, conversations, messages, tool calls, events, audit log

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UUID_PK = dict(server_default=sa.text("gen_random_uuid()"), nullable=False)
NOW = sa.text("now()")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False)


def upgrade() -> None:
    # Normally created by deploy/postgres/init-roles.sh; IF NOT EXISTS keeps this idempotent.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "customers",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column("status", sa.Text, server_default="anonymous", nullable=False),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_customers"),
        sa.CheckConstraint(_in("status", ("anonymous", "registered")), name=op.f("ck_customers_status")),
    )
    op.create_table(
        "customer_identities",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column("customer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_customer_identities"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE",
                                name="fk_customer_identities_customer_id_customers"),
        sa.UniqueConstraint("provider", "subject", name="uq_customer_identities_provider_subject"),
        sa.CheckConstraint(_in("provider", ("anon", "google", "phone")), name=op.f("ck_customer_identities_provider")),
    )
    op.create_index("ix_customer_identities_customer_id", "customer_identities", ["customer_id"])

    op.create_table(
        "conversations",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column("customer_id", pg.UUID(as_uuid=True)),
        sa.Column("channel", sa.Text, server_default="web", nullable=False),
        sa.Column("prompt_version", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("index_version", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE",
                                name="fk_conversations_customer_id_customers"),
        sa.CheckConstraint(_in("channel", ("web", "admin")), name=op.f("ck_conversations_channel")),
    )
    op.create_index("ix_conversations_customer_id_started_at", "conversations", ["customer_id", "started_at"])

    op.create_table(
        "messages",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column("conversation_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("script", sa.Text),
        sa.Column("tokens", sa.Integer),
        sa.Column("latency_ms", sa.Integer),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE",
                                name="fk_messages_conversation_id_conversations"),
        sa.CheckConstraint(_in("role", ("user", "assistant", "system", "tool")), name=op.f("ck_messages_role")),
        sa.CheckConstraint(_in("script", ("en", "ur", "roman_ur")), name=op.f("ck_messages_script")),
        sa.CheckConstraint("tokens >= 0", name=op.f("ck_messages_tokens_nonnegative")),
        sa.CheckConstraint("latency_ms >= 0", name=op.f("ck_messages_latency_nonnegative")),
    )
    op.create_index("ix_messages_conversation_id_created_at", "messages", ["conversation_id", "created_at"])

    op.create_table(
        "tool_calls",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column("message_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tool", sa.Text, nullable=False),
        sa.Column("arguments", pg.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("result_summary", sa.Text),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("duration_ms", sa.Integer),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_tool_calls"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE",
                                name="fk_tool_calls_message_id_messages"),
        sa.CheckConstraint(_in("status", ("ok", "error", "rejected", "timeout")), name=op.f("ck_tool_calls_status")),
        sa.CheckConstraint("duration_ms >= 0", name=op.f("ck_tool_calls_duration_nonnegative")),
    )
    op.create_index("ix_tool_calls_message_id", "tool_calls", ["message_id"])

    op.create_table(
        "events",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column("customer_id", pg.UUID(as_uuid=True)),
        sa.Column("session_id", sa.Text, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("payload", pg.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL",
                                name="fk_events_customer_id_customers"),
        sa.CheckConstraint(
            _in("type", ("view", "search", "impression", "click", "add_to_cart", "ui_action", "voice", "handoff")),
            name=op.f("ck_events_type"),
        ),
    )
    op.create_index("ix_events_type_created_at", "events", ["type", "created_at"])
    op.create_index("ix_events_customer_id_created_at", "events", ["customer_id", "created_at"])
    op.create_index("ix_events_session_id_created_at", "events", ["session_id", "created_at"])

    op.create_table(
        "audit_log",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column("actor_type", sa.Text, nullable=False),
        sa.Column("actor_id", sa.Text),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("target", sa.Text),
        sa.Column("before", pg.JSONB),
        sa.Column("after", pg.JSONB),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
        sa.CheckConstraint(_in("actor_type", ("system", "admin", "customer", "agent")), name=op.f("ck_audit_log_actor_type")),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    op.create_index("ix_audit_log_target_created_at", "audit_log", ["target", "created_at"])


def downgrade() -> None:
    # The vector extension is shared infrastructure and is deliberately left installed.
    for table in ("audit_log", "events", "tool_calls", "messages", "conversations",
                  "customer_identities", "customers"):
        op.drop_table(table)
