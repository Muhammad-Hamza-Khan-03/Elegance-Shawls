"""WhatsApp bridge: contacts, messages and enquiry linkage (expand-only, optional feature).

Adds two tables and nullable/defaulted columns on `enquiries`; nothing existing changes meaning. Inert while
WHATSAPP_BRIDGE_ENABLED=false. Downgrade REFUSES to run while chat rows exist unless ALEMBIC_ALLOW_WHATSAPP_DATA_LOSS=1.
"""
import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_contacts",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("chat_jid", sa.Text, nullable=False),
        sa.Column("lid", sa.Text),
        sa.Column("phone_e164", sa.Text),
        sa.Column("display_name", sa.Text),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="SET NULL")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_whatsapp_contacts"),
        sa.UniqueConstraint("chat_jid", name="uq_whatsapp_contacts_chat_jid"),
    )
    op.add_column("enquiries", sa.Column("status", sa.Text, server_default="handed_off", nullable=False))
    op.add_column("enquiries", sa.Column("whatsapp_contact_id", pg.UUID(as_uuid=True),
                                         sa.ForeignKey("whatsapp_contacts.id", ondelete="SET NULL")))
    op.add_column("enquiries", sa.Column("linked_at", sa.DateTime(timezone=True)))
    op.add_column("enquiries", sa.Column("link_source", sa.Text))
    op.add_column("enquiries", sa.Column("customer_details", pg.JSONB))
    op.add_column("enquiries", sa.Column("bot_paused_until", sa.DateTime(timezone=True)))
    op.create_check_constraint(op.f("ck_enquiries_status"), "enquiries",
                               "status IN ('handed_off', 'contacted', 'converted', 'lost')")
    op.create_check_constraint(op.f("ck_enquiries_link_source"), "enquiries",
                               "link_source IS NULL OR link_source IN ('reference', 'staff')")
    op.create_index("ix_enquiries_whatsapp_contact_id", "enquiries", ["whatsapp_contact_id", sa.text("created_at DESC")])

    op.create_table(
        "whatsapp_messages",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("wa_message_id", sa.Text, nullable=False),
        sa.Column("contact_id", pg.UUID(as_uuid=True), sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.Text, nullable=False),
        sa.Column("from_me", sa.Boolean, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("text", sa.Text),
        sa.Column("sent_by", sa.Text, nullable=False),
        sa.Column("quoted_wa_id", sa.Text),
        sa.Column("media_ref", sa.Text),
        sa.Column("enquiry_id", pg.UUID(as_uuid=True), sa.ForeignKey("enquiries.id", ondelete="SET NULL")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_whatsapp_messages"),
        sa.UniqueConstraint("wa_message_id", name="uq_whatsapp_messages_wa_message_id"),
        sa.CheckConstraint("direction IN ('in', 'out')", name=op.f("ck_whatsapp_messages_direction")),
        sa.CheckConstraint("type IN ('text', 'image', 'audio', 'video', 'document', 'other')", name=op.f("ck_whatsapp_messages_type")),
        sa.CheckConstraint("sent_by IN ('customer', 'staff', 'bot')", name=op.f("ck_whatsapp_messages_sent_by")),
    )
    op.create_index("ix_whatsapp_messages_contact_sent", "whatsapp_messages", ["contact_id", "sent_at"])
    op.create_index("ix_whatsapp_messages_enquiry_sent", "whatsapp_messages", ["enquiry_id", "sent_at"])


def downgrade() -> None:
    at_risk = op.get_bind().execute(sa.text("SELECT count(*) FROM whatsapp_messages")).scalar()
    if at_risk and os.environ.get("ALEMBIC_ALLOW_WHATSAPP_DATA_LOSS") != "1":
        raise RuntimeError(f"Refusing to downgrade 0019: {at_risk} stored WhatsApp messages would be lost. "
                           "Back up with pg_dump, then rerun with ALEMBIC_ALLOW_WHATSAPP_DATA_LOSS=1.")
    op.drop_table("whatsapp_messages")
    op.drop_index("ix_enquiries_whatsapp_contact_id", table_name="enquiries")
    op.drop_constraint(op.f("ck_enquiries_link_source"), "enquiries", type_="check")
    op.drop_constraint(op.f("ck_enquiries_status"), "enquiries", type_="check")
    for column in ("bot_paused_until", "customer_details", "link_source", "linked_at", "whatsapp_contact_id", "status"):
        op.drop_column("enquiries", column)
    op.drop_table("whatsapp_contacts")
