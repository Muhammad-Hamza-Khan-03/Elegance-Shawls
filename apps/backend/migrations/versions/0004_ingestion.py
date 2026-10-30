"""ingestion: jobs, staged products and the append-only review audit

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

NOW = sa.text("now()")
STAGED = ("pending_review", "approved", "rejected", "published", "unpublished", "archived")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("status", sa.Text, server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer, server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer, server_default="3", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("lease_owner", sa.Text),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("last_error", sa.Text),
        sa.Column("result", pg.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_jobs"),
        sa.UniqueConstraint("idempotency_key", name="uq_ingestion_jobs_idempotency_key"),
        sa.CheckConstraint(_in("status", ("queued", "running", "succeeded", "retrying", "failed", "cancelled")),
                           name=op.f("ck_ingestion_jobs_status")),
        sa.CheckConstraint("char_length(path) BETWEEN 1 AND 220", name=op.f("ck_ingestion_jobs_path_length")),
        sa.CheckConstraint("attempts >= 0 AND max_attempts >= 1 AND attempts <= max_attempts",
                           name=op.f("ck_ingestion_jobs_attempts_bounded")),
        sa.CheckConstraint("status <> 'running' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
                           name=op.f("ck_ingestion_jobs_lease_present_while_running")),
    )
    op.create_index("ix_ingestion_jobs_claimable", "ingestion_jobs", ["available_at"],
                    postgresql_where=sa.text("status IN ('queued', 'retrying') AND NOT cancel_requested"))
    op.create_index("ix_ingestion_jobs_running_lease", "ingestion_jobs", ["lease_expires_at"],
                    postgresql_where=sa.text("status = 'running'"))
    op.create_index("ix_ingestion_jobs_created_at_id", "ingestion_jobs", [sa.text("created_at DESC"), sa.text("id DESC")])

    op.create_table(
        "staged_products",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("source_product_id", sa.Text),
        sa.Column("source_content_hash", sa.Text, nullable=False),
        sa.Column("latest_source_hash", sa.Text),
        sa.Column("dedupe_key", sa.Text, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_job_id", pg.UUID(as_uuid=True)),
        sa.Column("source_price", sa.Numeric(12, 2)),
        sa.Column("source_currency", sa.CHAR(3)),
        sa.Column("status", sa.Text, server_default="pending_review", nullable=False),
        sa.Column("rejection_reason", sa.Text),
        sa.Column("product", pg.JSONB, nullable=False),
        sa.Column("source_attributes", pg.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("missing_fields", sa.ARRAY(sa.Text), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("stock_known", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("approved_price", sa.Integer),
        sa.Column("approved_stock", sa.Integer),
        sa.Column("product_id", pg.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_staged_products"),
        sa.ForeignKeyConstraint(["ingestion_job_id"], ["ingestion_jobs.id"], ondelete="SET NULL",
                                name="fk_staged_products_ingestion_job_id_ingestion_jobs"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT",
                                name="fk_staged_products_product_id_products"),
        sa.UniqueConstraint("source_id", "dedupe_key", name="uq_staged_products_source_id_dedupe_key"),
        sa.CheckConstraint(_in("status", STAGED), name=op.f("ck_staged_products_status")),
        sa.CheckConstraint("source_price >= 0", name=op.f("ck_staged_products_source_price_nonnegative")),
        sa.CheckConstraint("approved_price >= 0 AND approved_stock >= 0", name=op.f("ck_staged_products_approved_nonnegative")),
        sa.CheckConstraint("status <> 'rejected' OR (rejection_reason IS NOT NULL AND char_length(rejection_reason) >= 3)",
                           name=op.f("ck_staged_products_rejection_needs_reason")),
        sa.CheckConstraint(
            "status NOT IN ('approved', 'published', 'unpublished') "
            "OR (product_id IS NOT NULL AND approved_price IS NOT NULL AND stock_known)",
            name=op.f("ck_staged_products_approved_states_need_product")),
    )
    op.create_index("ix_staged_products_review_feed", "staged_products",
                    ["status", sa.text("created_at DESC"), sa.text("id DESC")])
    op.create_index("ix_staged_products_product_id", "staged_products", ["product_id"],
                    postgresql_where=sa.text("product_id IS NOT NULL"))
    op.create_index("ix_staged_products_ingestion_job_id", "staged_products", ["ingestion_job_id"],
                    postgresql_where=sa.text("ingestion_job_id IS NOT NULL"))

    op.create_table(
        "staged_product_audit",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("seq", sa.BigInteger, sa.Identity(always=True), nullable=False),
        sa.Column("staged_product_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("from_status", sa.Text),
        sa.Column("to_status", sa.Text),
        sa.Column("actor", sa.Text, server_default="admin", nullable=False),
        sa.Column("note", sa.Text),
        sa.PrimaryKeyConstraint("id", name="pk_staged_product_audit"),
        sa.ForeignKeyConstraint(["staged_product_id"], ["staged_products.id"], ondelete="RESTRICT",
                                name="fk_staged_product_audit_staged_product_id_staged_products"),
        sa.CheckConstraint(_in("from_status", STAGED), name=op.f("ck_staged_product_audit_from_status")),
        sa.CheckConstraint(_in("to_status", STAGED), name=op.f("ck_staged_product_audit_to_status")),
        sa.CheckConstraint("char_length(action) >= 1", name=op.f("ck_staged_product_audit_action_present")),
    )
    op.create_index("ix_staged_product_audit_staged_product_id_seq", "staged_product_audit", ["staged_product_id", "seq"])

    # Append-only: the review trail can be added to, never rewritten or erased.
    op.execute("""
        CREATE FUNCTION staged_product_audit_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'staged_product_audit is append-only (% not allowed)', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER staged_product_audit_append_only BEFORE UPDATE OR DELETE ON staged_product_audit
        FOR EACH ROW EXECUTE FUNCTION staged_product_audit_append_only()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS staged_product_audit_append_only ON staged_product_audit")
    op.execute("DROP FUNCTION IF EXISTS staged_product_audit_append_only()")
    op.drop_table("staged_product_audit")
    op.drop_table("staged_products")
    op.drop_table("ingestion_jobs")
