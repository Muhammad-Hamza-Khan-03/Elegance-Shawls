"""M4 Batch B synthetic recommendation impression provenance."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_impressions",
        sa.Column("id", pg.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("customer_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("recommendation_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("feature_flag", sa.Text(), nullable=False),
        sa.Column("experiment_arm", sa.Text(), nullable=False),
        sa.Column("preference_version", sa.Integer(), nullable=False),
        sa.Column("catalogue_revision", sa.Integer(), nullable=False),
        sa.Column("source_memory_ids", pg.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_recommendation_impressions"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL", name="fk_recommendation_impressions_customer_id_customers"),
        sa.UniqueConstraint("customer_id", "request_id", "experiment_arm", "position", name="uq_recommendation_impressions_request_position"),
        sa.CheckConstraint("position >= 0", name="ck_recommendation_impressions_position_nonnegative"),
        sa.CheckConstraint("request_id ~ '^[A-Za-z0-9_-]{16,128}$'", name="ck_recommendation_impressions_request_id_format"),
        sa.CheckConstraint("experiment_arm IN ('control', 'treatment')", name="ck_recommendation_impressions_experiment_arm"),
        sa.CheckConstraint("char_length(context) BETWEEN 1 AND 64", name="ck_recommendation_impressions_context_length"),
        sa.CheckConstraint("char_length(feature_flag) BETWEEN 1 AND 64", name="ck_recommendation_impressions_feature_flag_length"),
        sa.CheckConstraint("preference_version >= 0 AND catalogue_revision >= 1", name="ck_recommendation_impressions_versions_nonnegative"),
    )
    op.create_index("ix_recommendation_impressions_customer_created", "recommendation_impressions", ["customer_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM recommendation_impressions")).scalar():
        raise RuntimeError("Refusing to remove recommendation impression evidence")
    op.drop_index("ix_recommendation_impressions_customer_created", table_name="recommendation_impressions")
    op.drop_table("recommendation_impressions")
