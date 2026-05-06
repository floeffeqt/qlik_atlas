"""fix project-scoped RLS select policies to enforce customer access check

The previous _project_inherited_select policies only verified that the
referenced project row existed but did NOT verify that the current user
has customer access to the project's customer.  This migration replaces
those policies with a corrected USING clause that calls
app_has_customer_access(p.customer_id).

Revision ID: 0019_rls_customer_access
Revises: 0018_refresh_tokens
Create Date: 2026-03-13 00:00:00.000000
"""
from alembic import op


revision = "0019_rls_customer_access"
down_revision = "0018_refresh_tokens"
branch_labels = None
depends_on = None


# All tables that received the broken _project_inherited_select policy.
AFFECTED_TABLES = [
    # 0006
    "qlik_apps",
    "lineage_nodes",
    "lineage_edges",
    # 0007
    "qlik_spaces",
    "qlik_data_connections",
    "qlik_app_usage",
    "qlik_app_scripts",
    # 0015
    "qlik_reloads",
    "qlik_audits",
    "qlik_license_consumption",
    # 0016
    "qlik_license_status",
    # 0017
    "app_data_metadata_snapshot",
    "app_data_metadata_fields",
    "app_data_metadata_tables",
    "table_profiles",
    "field_profiles",
    "field_most_frequent",
    "field_frequency_distribution",
]


def upgrade() -> None:
    for table_name in AFFECTED_TABLES:
        policy_name = f"{table_name}_project_inherited_select"

        # Drop the old (broken) policy.
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON public.{table_name}")

        # Recreate with customer access check.
        op.execute(
            f"""
            CREATE POLICY {policy_name}
            ON public.{table_name}
            FOR SELECT
            USING (
                public.app_is_admin()
                OR EXISTS (
                    SELECT 1 FROM public.projects p
                    WHERE p.id = {table_name}.project_id
                      AND public.app_has_customer_access(p.customer_id)
                )
            );
            """
        )


def downgrade() -> None:
    # Restore the original (project-existence-only) policies.
    for table_name in AFFECTED_TABLES:
        policy_name = f"{table_name}_project_inherited_select"

        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON public.{table_name}")

        op.execute(
            f"""
            CREATE POLICY {policy_name}
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