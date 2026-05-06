"""add DB runtime tables for spaces/connections/usage/scripts and edge app mapping

Revision ID: 0007_db_runtime_source_tables
Revises: 0006_user_customer_access_rls
Create Date: 2026-02-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0007_db_runtime_source_tables"
down_revision = "0006_user_customer_access_rls"
branch_labels = None
depends_on = None


PROJECT_SCOPED_TABLES = [
    "qlik_spaces",
    "qlik_data_connections",
    "qlik_app_usage",
    "qlik_app_scripts",
]


def _enable_project_scoped_rls(table_name: str) -> None:
    op.execute(f'ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE public.{table_name} FORCE ROW LEVEL SECURITY')
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
    op.execute(f'ALTER TABLE public.{table_name} NO FORCE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY')


def upgrade() -> None:
    op.add_column("lineage_edges", sa.Column("app_id", sa.String(length=100), nullable=True))
    op.create_index("ix_lineage_edges_app_id", "lineage_edges", ["app_id"])

    op.create_table(
        "qlik_spaces",
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("space_id", sa.String(length=100), nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("project_id", "space_id"),
    )
    op.create_index("ix_qlik_spaces_project_id", "qlik_spaces", ["project_id"])

    op.create_table(
        "qlik_data_connections",
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.String(length=120), nullable=False),
        sa.Column("space_id", sa.String(length=100), nullable=True),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("project_id", "connection_id"),
    )
    op.create_index("ix_qlik_data_connections_project_id", "qlik_data_connections", ["project_id"])
    op.create_index("ix_qlik_data_connections_space_id", "qlik_data_connections", ["space_id"])

    op.create_table(
        "qlik_app_usage",
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("app_id", sa.String(length=100), nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("project_id", "app_id"),
    )
    op.create_index("ix_qlik_app_usage_project_id", "qlik_app_usage", ["project_id"])

    op.create_table(
        "qlik_app_scripts",
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("app_id", sa.String(length=100), nullable=False),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("project_id", "app_id"),
    )
    op.create_index("ix_qlik_app_scripts_project_id", "qlik_app_scripts", ["project_id"])

    for table_name in PROJECT_SCOPED_TABLES:
        _enable_project_scoped_rls(table_name)


def downgrade() -> None:
    for table_name in reversed(PROJECT_SCOPED_TABLES):
        _disable_project_scoped_rls(table_name)

    op.drop_index("ix_qlik_app_scripts_project_id", table_name="qlik_app_scripts")
    op.drop_table("qlik_app_scripts")

    op.drop_index("ix_qlik_app_usage_project_id", table_name="qlik_app_usage")
    op.drop_table("qlik_app_usage")

    op.drop_index("ix_qlik_data_connections_space_id", table_name="qlik_data_connections")
    op.drop_index("ix_qlik_data_connections_project_id", table_name="qlik_data_connections")
    op.drop_table("qlik_data_connections")

    op.drop_index("ix_qlik_spaces_project_id", table_name="qlik_spaces")
    op.drop_table("qlik_spaces")

    op.drop_index("ix_lineage_edges_app_id", table_name="lineage_edges")
    op.drop_column("lineage_edges", "app_id")
