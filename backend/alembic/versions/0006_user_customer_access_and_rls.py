"""add user-customer access mapping and PostgreSQL row-level security

Revision ID: 0006_user_customer_access_and_rls
Revises: 0005_customer_credentials_aesgcm_storage
Create Date: 2026-02-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_user_customer_access_rls"
down_revision = "0005_customer_credentials_aesgcm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_customer_access",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("user_id", "customer_id"),
    )
    op.create_index("ix_user_customer_access_user_id", "user_customer_access", ["user_id"])
    op.create_index("ix_user_customer_access_customer_id", "user_customer_access", ["customer_id"])

    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.app_current_user_id()
        RETURNS integer
        LANGUAGE sql
        STABLE
        AS $$
            SELECT NULLIF(current_setting('app.user_id', true), '')::integer
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.app_current_role()
        RETURNS text
        LANGUAGE sql
        STABLE
        AS $$
            SELECT NULLIF(current_setting('app.role', true), '')
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.app_is_admin()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
            SELECT public.app_current_role() = 'admin'
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.app_has_customer_access(p_customer_id integer)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM public.user_customer_access uca
                WHERE uca.user_id = public.app_current_user_id()
                  AND uca.customer_id = p_customer_id
            )
        $$;
        """
    )

    for table_name in ["customers", "projects", "qlik_apps", "lineage_nodes", "lineage_edges"]:
        op.execute(f'ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public.{table_name} FORCE ROW LEVEL SECURITY')

    # Customers: admin full access; non-admin users can read assigned customers only.
    op.execute(
        """
        CREATE POLICY customers_admin_all
        ON public.customers
        FOR ALL
        USING (public.app_is_admin())
        WITH CHECK (public.app_is_admin());
        """
    )
    op.execute(
        """
        CREATE POLICY customers_assigned_select
        ON public.customers
        FOR SELECT
        USING (public.app_is_admin() OR public.app_has_customer_access(id));
        """
    )

    # Projects: admin full access; non-admin users can CRUD projects within assigned customers.
    op.execute(
        """
        CREATE POLICY projects_customer_access_all
        ON public.projects
        FOR ALL
        USING (public.app_is_admin() OR public.app_has_customer_access(customer_id))
        WITH CHECK (public.app_is_admin() OR public.app_has_customer_access(customer_id));
        """
    )

    # Project-scoped graph tables: reads inherit from visible projects; writes remain admin-only.
    op.execute(
        """
        CREATE POLICY qlik_apps_admin_write
        ON public.qlik_apps
        FOR INSERT
        WITH CHECK (public.app_is_admin());
        """
    )
    op.execute(
        """
        CREATE POLICY qlik_apps_admin_update
        ON public.qlik_apps
        FOR UPDATE
        USING (public.app_is_admin())
        WITH CHECK (public.app_is_admin());
        """
    )
    op.execute(
        """
        CREATE POLICY qlik_apps_admin_delete
        ON public.qlik_apps
        FOR DELETE
        USING (public.app_is_admin());
        """
    )
    op.execute(
        """
        CREATE POLICY qlik_apps_project_inherited_select
        ON public.qlik_apps
        FOR SELECT
        USING (
            public.app_is_admin()
            OR EXISTS (
                SELECT 1 FROM public.projects p
                WHERE p.id = qlik_apps.project_id
            )
        );
        """
    )

    for table_name in ["lineage_nodes", "lineage_edges"]:
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


def downgrade() -> None:
    for table_name in ["lineage_edges", "lineage_nodes"]:
        for policy_name in [
            f"{table_name}_project_inherited_select",
            f"{table_name}_admin_write_delete",
            f"{table_name}_admin_write_update",
            f"{table_name}_admin_write_insert",
        ]:
            op.execute(f"DROP POLICY IF EXISTS {policy_name} ON public.{table_name}")

    for policy_name in [
        "qlik_apps_project_inherited_select",
        "qlik_apps_admin_delete",
        "qlik_apps_admin_update",
        "qlik_apps_admin_write",
    ]:
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON public.qlik_apps")

    op.execute("DROP POLICY IF EXISTS projects_customer_access_all ON public.projects")
    op.execute("DROP POLICY IF EXISTS customers_assigned_select ON public.customers")
    op.execute("DROP POLICY IF EXISTS customers_admin_all ON public.customers")

    for table_name in ["lineage_edges", "lineage_nodes", "qlik_apps", "projects", "customers"]:
        op.execute(f'ALTER TABLE public.{table_name} NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY')

    op.execute("DROP FUNCTION IF EXISTS public.app_has_customer_access(integer)")
    op.execute("DROP FUNCTION IF EXISTS public.app_is_admin()")
    op.execute("DROP FUNCTION IF EXISTS public.app_current_role()")
    op.execute("DROP FUNCTION IF EXISTS public.app_current_user_id()")

    op.drop_index("ix_user_customer_access_customer_id", table_name="user_customer_access")
    op.drop_index("ix_user_customer_access_user_id", table_name="user_customer_access")
    op.drop_table("user_customer_access")
