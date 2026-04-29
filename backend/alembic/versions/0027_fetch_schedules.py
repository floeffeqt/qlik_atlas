"""fetch_schedules: scheduled fetch job table

Revision ID: 0027_fetch_schedules
Revises: 0026_customer_link
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0027_fetch_schedules"
down_revision = "0026_customer_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fetch_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("cron_expr", sa.String(100), nullable=False),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fetch_schedules_project_id", "fetch_schedules", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_fetch_schedules_project_id", table_name="fetch_schedules")
    op.drop_table("fetch_schedules")
