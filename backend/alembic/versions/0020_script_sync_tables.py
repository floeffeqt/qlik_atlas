"""add script_git_mappings and script_deployments tables for git-based script sync

Revision ID: 0020_script_sync_tables
Revises: 0019_rls_customer_access
Create Date: 2026-03-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0020_script_sync_tables"
down_revision = "0019_rls_customer_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Git credentials on customers --
    op.add_column("customers", sa.Column("git_provider", sa.String(20), nullable=True))
    op.add_column("customers", sa.Column("git_token", sa.Text, nullable=True))
    op.add_column("customers", sa.Column("git_base_url", sa.String(500), nullable=True))

    # -- Mapping: which app <-> which repo/file --
    op.create_table(
        "script_git_mappings",
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("app_id", sa.String(100), nullable=False),
        sa.Column("repo_identifier", sa.String(500), nullable=False),
        sa.Column("branch", sa.String(200), nullable=False, server_default="main"),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("last_git_commit_sha", sa.String(64), nullable=True),
        sa.Column("last_git_script_hash", sa.String(64), nullable=True),
        sa.Column("last_qlik_script_hash", sa.String(64), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint("project_id", "app_id"),
    )

    # -- Audit log: every sync/publish is recorded --
    op.create_table(
        "script_deployments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("app_id", sa.String(100), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("git_commit_sha", sa.String(64), nullable=True),
        sa.Column("git_script_hash", sa.String(64), nullable=True),
        sa.Column("qlik_script_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("triggered_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("version_message", sa.Text, nullable=True),
        sa.Column("error_detail", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- RLS policies --
    op.execute("""
        CREATE POLICY script_git_mappings_project_inherited_select
        ON public.script_git_mappings
        FOR SELECT
        USING (
            public.app_is_admin()
            OR EXISTS (
                SELECT 1 FROM public.projects p
                WHERE p.id = script_git_mappings.project_id
                  AND public.app_has_customer_access(p.customer_id)
            )
        );
    """)
    op.execute("ALTER TABLE public.script_git_mappings ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE public.script_git_mappings FORCE ROW LEVEL SECURITY;")

    op.execute("""
        CREATE POLICY script_deployments_project_inherited_select
        ON public.script_deployments
        FOR SELECT
        USING (
            public.app_is_admin()
            OR EXISTS (
                SELECT 1 FROM public.projects p
                WHERE p.id = script_deployments.project_id
                  AND public.app_has_customer_access(p.customer_id)
            )
        );
    """)
    op.execute("ALTER TABLE public.script_deployments ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE public.script_deployments FORCE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS script_deployments_project_inherited_select ON public.script_deployments;")
    op.execute("DROP POLICY IF EXISTS script_git_mappings_project_inherited_select ON public.script_git_mappings;")
    op.drop_table("script_deployments")
    op.drop_table("script_git_mappings")
    op.drop_column("customers", "git_base_url")
    op.drop_column("customers", "git_token")
    op.drop_column("customers", "git_provider")