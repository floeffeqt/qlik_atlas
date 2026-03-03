"""align license consumption schema and add license status table

Revision ID: 0016_license_schema_status
Revises: 0015_qcloud_ingestion
Create Date: 2026-03-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0016_license_schema_status"
down_revision = "0015_qcloud_ingestion"
branch_labels = None
depends_on = None


PROJECT_SCOPED_TABLES = [
    "qlik_license_status",
]


def _enable_project_scoped_rls(table_name: str) -> None:
    op.execute(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table_name}_admin_write_insert
        ON public.{table_name}
        FOR INSERT
        WITH CHECK (public.app_is_admin());
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table_name}_admin_write_update
        ON public.{table_name}
        FOR UPDATE
        USING (public.app_is_admin())
        WITH CHECK (public.app_is_admin());
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table_name}_admin_write_delete
        ON public.{table_name}
        FOR DELETE
        USING (public.app_is_admin());
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table_name}_project_inherited_select
        ON public.{table_name}
        FOR SELECT
        USING (
            public.app_is_admin()
            OR EXISTS (
                SELECT 1 FROM public.projects p
                WHERE p.id = {table_name}.project_id
            )
        );
        """
    )


def _disable_project_scoped_rls(table_name: str) -> None:
    for policy_name in [
        f"{table_name}_project_inherited_select",
        f"{table_name}_admin_write_delete",
        f"{table_name}_admin_write_update",
        f"{table_name}_admin_write_insert",
    ]:
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON public.{table_name}")
    op.execute(f"ALTER TABLE public.{table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.add_column("qlik_license_consumption", sa.Column("appId", sa.String(length=120), nullable=True))
    op.add_column("qlik_license_consumption", sa.Column("userId", sa.String(length=120), nullable=True))
    op.add_column("qlik_license_consumption", sa.Column("endTime", sa.Text(), nullable=True))
    op.add_column("qlik_license_consumption", sa.Column("duration", sa.String(length=120), nullable=True))
    op.add_column("qlik_license_consumption", sa.Column("sessionId", sa.String(length=255), nullable=True))
    op.add_column("qlik_license_consumption", sa.Column("allotmentId", sa.String(length=255), nullable=True))
    op.add_column("qlik_license_consumption", sa.Column("minutesUsed", sa.Integer(), nullable=True))
    op.add_column("qlik_license_consumption", sa.Column("capacityUsed", sa.Integer(), nullable=True))
    op.add_column("qlik_license_consumption", sa.Column("licenseUsage", sa.String(length=120), nullable=True))

    op.create_index("ix_qlik_license_consumption_appId", "qlik_license_consumption", ["appId"])
    op.create_index("ix_qlik_license_consumption_userId", "qlik_license_consumption", ["userId"])
    op.create_index("ix_qlik_license_consumption_sessionId", "qlik_license_consumption", ["sessionId"])

    op.create_table(
        "qlik_license_status",
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status_id", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=120), nullable=True),
        sa.Column("trial", sa.Boolean(), nullable=True),
        sa.Column("valid", sa.Boolean(), nullable=True),
        sa.Column("origin", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=120), nullable=True),
        sa.Column("product", sa.String(length=255), nullable=True),
        sa.Column("deactivated", sa.Boolean(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("tenant", sa.String(length=255), nullable=True),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("project_id", "status_id"),
    )
    op.create_index("ix_qlik_license_status_project_id", "qlik_license_status", ["project_id"])

    for table_name in PROJECT_SCOPED_TABLES:
        _enable_project_scoped_rls(table_name)


def downgrade() -> None:
    for table_name in reversed(PROJECT_SCOPED_TABLES):
        _disable_project_scoped_rls(table_name)

    op.drop_index("ix_qlik_license_status_project_id", table_name="qlik_license_status")
    op.drop_table("qlik_license_status")

    op.drop_index("ix_qlik_license_consumption_sessionId", table_name="qlik_license_consumption")
    op.drop_index("ix_qlik_license_consumption_userId", table_name="qlik_license_consumption")
    op.drop_index("ix_qlik_license_consumption_appId", table_name="qlik_license_consumption")

    op.drop_column("qlik_license_consumption", "licenseUsage")
    op.drop_column("qlik_license_consumption", "capacityUsed")
    op.drop_column("qlik_license_consumption", "minutesUsed")
    op.drop_column("qlik_license_consumption", "allotmentId")
    op.drop_column("qlik_license_consumption", "sessionId")
    op.drop_column("qlik_license_consumption", "duration")
    op.drop_column("qlik_license_consumption", "endTime")
    op.drop_column("qlik_license_consumption", "userId")
    op.drop_column("qlik_license_consumption", "appId")
