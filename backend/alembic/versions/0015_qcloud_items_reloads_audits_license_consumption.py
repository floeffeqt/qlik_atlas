"""add qlik cloud ingestion tables and flatten item columns

Revision ID: 0015_qcloud_ingestion
Revises: 0014_alembic_verlen
Create Date: 2026-03-02 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0015_qcloud_ingestion"
down_revision = "0014_alembic_verlen"
branch_labels = None
depends_on = None


PROJECT_SCOPED_TABLES = [
    "qlik_reloads",
    "qlik_audits",
    "qlik_license_consumption",
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
    op.add_column("qlik_apps", sa.Column("id", sa.String(length=120), nullable=True))
    op.add_column("qlik_apps", sa.Column("ownerId", sa.String(length=120), nullable=True))
    op.add_column("qlik_apps", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("qlik_apps", sa.Column("resourceType", sa.String(length=120), nullable=True))
    op.add_column("qlik_apps", sa.Column("resourceId", sa.String(length=120), nullable=True))
    op.add_column("qlik_apps", sa.Column("thumbnail", sa.String(length=1024), nullable=True))
    op.add_column("qlik_apps", sa.Column("resourceAttributes_id", sa.String(length=120), nullable=True))
    op.add_column("qlik_apps", sa.Column("resourceAttributes_name", sa.String(length=255), nullable=True))
    op.add_column("qlik_apps", sa.Column("resourceAttributes_description", sa.Text(), nullable=True))
    op.add_column("qlik_apps", sa.Column("resourceAttributes_createdDate", sa.Text(), nullable=True))
    op.add_column("qlik_apps", sa.Column("resourceAttributes_modifiedDate", sa.Text(), nullable=True))
    op.add_column("qlik_apps", sa.Column("resourceAttributes_modifiedByUserName", sa.String(length=255), nullable=True))
    op.add_column("qlik_apps", sa.Column("resourceAttributes_publishTime", sa.Text(), nullable=True))
    op.add_column("qlik_apps", sa.Column("resourceAttributes_lastReloadTime", sa.Text(), nullable=True))
    op.add_column("qlik_apps", sa.Column("resourceAttributes_trashed", sa.Boolean(), nullable=True))
    op.add_column("qlik_apps", sa.Column("resourceCustomAttributes_json", JSONB(), nullable=True))
    op.add_column("qlik_apps", sa.Column("source", sa.String(length=255), nullable=True))
    op.add_column("qlik_apps", sa.Column("tenant", sa.String(length=255), nullable=True))

    op.create_table(
        "qlik_reloads",
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reload_id", sa.String(length=120), nullable=False),
        sa.Column("app_id", sa.String(length=100), nullable=True),
        sa.Column("log", sa.Text(), nullable=True),
        sa.Column("type", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=120), nullable=True),
        sa.Column("userId", sa.String(length=120), nullable=True),
        sa.Column("weight", sa.Integer(), nullable=True),
        sa.Column("endTime", sa.Text(), nullable=True),
        sa.Column("partial", sa.Boolean(), nullable=True),
        sa.Column("tenantId", sa.String(length=120), nullable=True),
        sa.Column("errorCode", sa.String(length=120), nullable=True),
        sa.Column("errorMessage", sa.Text(), nullable=True),
        sa.Column("startTime", sa.Text(), nullable=True),
        sa.Column("engineTime", sa.Text(), nullable=True),
        sa.Column("creationTime", sa.Text(), nullable=True),
        sa.Column("createdDate", sa.Text(), nullable=True),
        sa.Column("created_date_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modifiedDate", sa.Text(), nullable=True),
        sa.Column("modifiedByUserName", sa.String(length=255), nullable=True),
        sa.Column("ownerId", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logAvailable", sa.Boolean(), nullable=True),
        sa.Column("operational_id", sa.String(length=120), nullable=True),
        sa.Column("operational_nextExecution", sa.Text(), nullable=True),
        sa.Column("operational_timesExecuted", sa.Integer(), nullable=True),
        sa.Column("operational_state", sa.String(length=120), nullable=True),
        sa.Column("operational_hash", sa.String(length=255), nullable=True),
        sa.Column("links_self_href", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("tenant", sa.String(length=255), nullable=True),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("project_id", "reload_id"),
    )
    op.create_index("ix_qlik_reloads_project_id", "qlik_reloads", ["project_id"])
    op.create_index("ix_qlik_reloads_app_id", "qlik_reloads", ["app_id"])
    op.create_index("ix_qlik_reloads_created_date_ts", "qlik_reloads", ["created_date_ts"])

    op.create_table(
        "qlik_audits",
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audit_id", sa.String(length=200), nullable=False),
        sa.Column("userId", sa.String(length=120), nullable=True),
        sa.Column("eventId", sa.String(length=120), nullable=True),
        sa.Column("tenantId", sa.String(length=120), nullable=True),
        sa.Column("eventTime", sa.Text(), nullable=True),
        sa.Column("eventType", sa.String(length=255), nullable=True),
        sa.Column("links_self_href", sa.Text(), nullable=True),
        sa.Column("extensions_actor_sub", sa.String(length=255), nullable=True),
        sa.Column("time", sa.Text(), nullable=True),
        sa.Column("time_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subType", sa.String(length=120), nullable=True),
        sa.Column("spaceId", sa.String(length=120), nullable=True),
        sa.Column("spaceType", sa.String(length=120), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("type", sa.String(length=120), nullable=True),
        sa.Column("actorId", sa.String(length=255), nullable=True),
        sa.Column("actorType", sa.String(length=120), nullable=True),
        sa.Column("origin", sa.String(length=255), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("ipAddress", sa.String(length=120), nullable=True),
        sa.Column("userAgent", sa.Text(), nullable=True),
        sa.Column("properties_appId", sa.String(length=120), nullable=True),
        sa.Column("data_message", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("tenant", sa.String(length=255), nullable=True),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("project_id", "audit_id"),
    )
    op.create_index("ix_qlik_audits_project_id", "qlik_audits", ["project_id"])
    op.create_index("ix_qlik_audits_properties_appId", "qlik_audits", ["properties_appId"])
    op.create_index("ix_qlik_audits_time_ts", "qlik_audits", ["time_ts"])

    op.create_table(
        "qlik_license_consumption",
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consumption_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("displayName", sa.String(length=255), nullable=True),
        sa.Column("type", sa.String(length=120), nullable=True),
        sa.Column("excess", sa.Integer(), nullable=True),
        sa.Column("allocated", sa.Integer(), nullable=True),
        sa.Column("available", sa.Integer(), nullable=True),
        sa.Column("used", sa.Integer(), nullable=True),
        sa.Column("quarantined", sa.Integer(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("tenant", sa.String(length=255), nullable=True),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("project_id", "consumption_id"),
    )
    op.create_index("ix_qlik_license_consumption_project_id", "qlik_license_consumption", ["project_id"])

    for table_name in PROJECT_SCOPED_TABLES:
        _enable_project_scoped_rls(table_name)


def downgrade() -> None:
    for table_name in reversed(PROJECT_SCOPED_TABLES):
        _disable_project_scoped_rls(table_name)

    op.drop_index("ix_qlik_license_consumption_project_id", table_name="qlik_license_consumption")
    op.drop_table("qlik_license_consumption")

    op.drop_index("ix_qlik_audits_time_ts", table_name="qlik_audits")
    op.drop_index("ix_qlik_audits_properties_appId", table_name="qlik_audits")
    op.drop_index("ix_qlik_audits_project_id", table_name="qlik_audits")
    op.drop_table("qlik_audits")

    op.drop_index("ix_qlik_reloads_created_date_ts", table_name="qlik_reloads")
    op.drop_index("ix_qlik_reloads_app_id", table_name="qlik_reloads")
    op.drop_index("ix_qlik_reloads_project_id", table_name="qlik_reloads")
    op.drop_table("qlik_reloads")

    op.drop_column("qlik_apps", "tenant")
    op.drop_column("qlik_apps", "source")
    op.drop_column("qlik_apps", "resourceCustomAttributes_json")
    op.drop_column("qlik_apps", "resourceAttributes_trashed")
    op.drop_column("qlik_apps", "resourceAttributes_lastReloadTime")
    op.drop_column("qlik_apps", "resourceAttributes_publishTime")
    op.drop_column("qlik_apps", "resourceAttributes_modifiedByUserName")
    op.drop_column("qlik_apps", "resourceAttributes_modifiedDate")
    op.drop_column("qlik_apps", "resourceAttributes_createdDate")
    op.drop_column("qlik_apps", "resourceAttributes_description")
    op.drop_column("qlik_apps", "resourceAttributes_name")
    op.drop_column("qlik_apps", "resourceAttributes_id")
    op.drop_column("qlik_apps", "thumbnail")
    op.drop_column("qlik_apps", "resourceId")
    op.drop_column("qlik_apps", "resourceType")
    op.drop_column("qlik_apps", "description")
    op.drop_column("qlik_apps", "ownerId")
    op.drop_column("qlik_apps", "id")
