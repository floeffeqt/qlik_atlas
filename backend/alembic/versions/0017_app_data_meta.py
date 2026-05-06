"""add app data metadata ingestion tables

Revision ID: 0017_app_data_meta
Revises: 0016_license_schema_status
Create Date: 2026-03-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ARRAY


revision = "0017_app_data_meta"
down_revision = "0016_license_schema_status"
branch_labels = None
depends_on = None


PROJECT_SCOPED_TABLES = [
    "app_data_metadata_snapshot",
    "app_data_metadata_fields",
    "app_data_metadata_tables",
    "table_profiles",
    "field_profiles",
    "field_most_frequent",
    "field_frequency_distribution",
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
    op.create_table(
        "app_data_metadata_snapshot",
        sa.Column("snapshot_id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("app_id", sa.String(length=100), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("static_byte_size", sa.BigInteger(), nullable=True),
        sa.Column("has_section_access", sa.Boolean(), nullable=True),
        sa.Column("is_direct_query_mode", sa.Boolean(), nullable=True),
        sa.Column("reload_meta_cpu_time_spent_ms", sa.BigInteger(), nullable=True),
        sa.Column("reload_meta_peak_memory_bytes", sa.BigInteger(), nullable=True),
        sa.Column("reload_meta_full_reload_peak_memory_bytes", sa.BigInteger(), nullable=True),
        sa.Column("reload_meta_partial_reload_peak_memory_bytes", sa.BigInteger(), nullable=True),
        sa.Column("reload_meta_hardware_total_memory", sa.BigInteger(), nullable=True),
        sa.Column("reload_meta_hardware_logical_cores", sa.Integer(), nullable=True),
        sa.Column("schema_hash", sa.String(length=64), nullable=False),
        sa.Column("extra_json", JSONB(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("tenant", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_app_data_metadata_snapshot_project_id", "app_data_metadata_snapshot", ["project_id"])
    op.create_index("ix_app_data_metadata_snapshot_app_id", "app_data_metadata_snapshot", ["app_id"])
    op.create_index("ix_app_data_metadata_snapshot_fetched_at", "app_data_metadata_snapshot", ["fetched_at"])
    op.execute(
        "CREATE INDEX ix_app_data_meta_app_fetch_desc "
        "ON public.app_data_metadata_snapshot (app_id, fetched_at DESC)"
    )

    op.create_table(
        "app_data_metadata_fields",
        sa.Column("row_id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("app_data_metadata_snapshot.snapshot_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_hash", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("cardinal", sa.BigInteger(), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("is_hidden", sa.Boolean(), nullable=True),
        sa.Column("is_locked", sa.Boolean(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=True),
        sa.Column("is_numeric", sa.Boolean(), nullable=True),
        sa.Column("is_semantic", sa.Boolean(), nullable=True),
        sa.Column("total_count", sa.BigInteger(), nullable=True),
        sa.Column("distinct_only", sa.Boolean(), nullable=True),
        sa.Column("always_one_selected", sa.Boolean(), nullable=True),
        sa.Column("tags", ARRAY(sa.Text()), nullable=True),
        sa.Column("src_tables", ARRAY(sa.Text()), nullable=True),
        sa.Column("extra_json", JSONB(), nullable=True),
        sa.UniqueConstraint("snapshot_id", "field_hash"),
    )
    op.create_index("ix_app_data_metadata_fields_project_id", "app_data_metadata_fields", ["project_id"])
    op.create_index("ix_app_data_metadata_fields_snapshot_id", "app_data_metadata_fields", ["snapshot_id"])

    op.create_table(
        "app_data_metadata_tables",
        sa.Column("row_id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("app_data_metadata_snapshot.snapshot_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_loose", sa.Boolean(), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=True),
        sa.Column("is_semantic", sa.Boolean(), nullable=True),
        sa.Column("no_of_rows", sa.BigInteger(), nullable=True),
        sa.Column("no_of_fields", sa.Integer(), nullable=True),
        sa.Column("no_of_key_fields", sa.Integer(), nullable=True),
        sa.Column("extra_json", JSONB(), nullable=True),
        sa.UniqueConstraint("snapshot_id", "name"),
    )
    op.create_index("ix_app_data_metadata_tables_project_id", "app_data_metadata_tables", ["project_id"])
    op.create_index("ix_app_data_metadata_tables_snapshot_id", "app_data_metadata_tables", ["snapshot_id"])

    op.create_table(
        "table_profiles",
        sa.Column("table_profile_id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("app_data_metadata_snapshot.snapshot_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile_index", sa.Integer(), nullable=False),
        sa.Column("no_of_rows", sa.BigInteger(), nullable=True),
        sa.Column("extra_json", JSONB(), nullable=True),
        sa.UniqueConstraint("snapshot_id", "profile_index"),
    )
    op.create_index("ix_table_profiles_project_id", "table_profiles", ["project_id"])
    op.create_index("ix_table_profiles_snapshot_id", "table_profiles", ["snapshot_id"])

    op.create_table(
        "field_profiles",
        sa.Column("field_profile_id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("app_data_metadata_snapshot.snapshot_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "table_profile_id",
            sa.BigInteger(),
            sa.ForeignKey("table_profiles.table_profile_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("std_value", sa.Float(), nullable=True),
        sa.Column("sum_value", sa.Float(), nullable=True),
        sa.Column("sum2_value", sa.Float(), nullable=True),
        sa.Column("median_value", sa.Float(), nullable=True),
        sa.Column("average_value", sa.Float(), nullable=True),
        sa.Column("kurtosis", sa.Float(), nullable=True),
        sa.Column("skewness", sa.Float(), nullable=True),
        sa.Column("field_tags", ARRAY(sa.Text()), nullable=True),
        sa.Column("fractiles", JSONB(), nullable=True),
        sa.Column("neg_values", sa.BigInteger(), nullable=True),
        sa.Column("pos_values", sa.BigInteger(), nullable=True),
        sa.Column("last_sorted", sa.Text(), nullable=True),
        sa.Column("null_values", sa.BigInteger(), nullable=True),
        sa.Column("text_values", sa.BigInteger(), nullable=True),
        sa.Column("zero_values", sa.BigInteger(), nullable=True),
        sa.Column("first_sorted", sa.Text(), nullable=True),
        sa.Column("avg_string_len", sa.Float(), nullable=True),
        sa.Column("data_evenness", sa.Float(), nullable=True),
        sa.Column("empty_strings", sa.BigInteger(), nullable=True),
        sa.Column("max_string_len", sa.BigInteger(), nullable=True),
        sa.Column("min_string_len", sa.BigInteger(), nullable=True),
        sa.Column("sum_string_len", sa.BigInteger(), nullable=True),
        sa.Column("numeric_values", sa.BigInteger(), nullable=True),
        sa.Column("distinct_values", sa.BigInteger(), nullable=True),
        sa.Column("distinct_text_values", sa.BigInteger(), nullable=True),
        sa.Column("distinct_numeric_values", sa.BigInteger(), nullable=True),
        sa.Column("number_format_dec", sa.String(length=32), nullable=True),
        sa.Column("number_format_fmt", sa.String(length=120), nullable=True),
        sa.Column("number_format_thou", sa.String(length=32), nullable=True),
        sa.Column("number_format_ndec", sa.Integer(), nullable=True),
        sa.Column("number_format_use_thou", sa.Integer(), nullable=True),
        sa.Column("extra_json", JSONB(), nullable=True),
        sa.UniqueConstraint("table_profile_id", "profile_index"),
    )
    op.create_index("ix_field_profiles_project_id", "field_profiles", ["project_id"])
    op.create_index("ix_field_profiles_snapshot_id", "field_profiles", ["snapshot_id"])
    op.create_index("ix_field_profiles_table_profile_id", "field_profiles", ["table_profile_id"])

    op.create_table(
        "field_most_frequent",
        sa.Column("row_id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("app_data_metadata_snapshot.snapshot_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "field_profile_id",
            sa.BigInteger(),
            sa.ForeignKey("field_profiles.field_profile_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("symbol_text", sa.Text(), nullable=True),
        sa.Column("symbol_number", sa.Float(), nullable=True),
        sa.Column("frequency", sa.BigInteger(), nullable=True),
        sa.Column("extra_json", JSONB(), nullable=True),
        sa.UniqueConstraint("field_profile_id", "rank"),
    )
    op.create_index("ix_field_most_frequent_project_id", "field_most_frequent", ["project_id"])
    op.create_index("ix_field_most_frequent_snapshot_id", "field_most_frequent", ["snapshot_id"])
    op.create_index("ix_field_most_frequent_field_profile_id", "field_most_frequent", ["field_profile_id"])

    op.create_table(
        "field_frequency_distribution",
        sa.Column("row_id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("app_data_metadata_snapshot.snapshot_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "field_profile_id",
            sa.BigInteger(),
            sa.ForeignKey("field_profiles.field_profile_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bin_index", sa.Integer(), nullable=False),
        sa.Column("bin_edge", sa.Float(), nullable=True),
        sa.Column("frequency", sa.BigInteger(), nullable=True),
        sa.Column("number_of_bins", sa.Integer(), nullable=True),
        sa.Column("extra_json", JSONB(), nullable=True),
        sa.UniqueConstraint("field_profile_id", "bin_index"),
    )
    op.create_index(
        "ix_field_frequency_distribution_project_id",
        "field_frequency_distribution",
        ["project_id"],
    )
    op.create_index(
        "ix_field_frequency_distribution_snapshot_id",
        "field_frequency_distribution",
        ["snapshot_id"],
    )
    op.create_index(
        "ix_field_frequency_distribution_field_profile_id",
        "field_frequency_distribution",
        ["field_profile_id"],
    )

    for table_name in PROJECT_SCOPED_TABLES:
        _enable_project_scoped_rls(table_name)


def downgrade() -> None:
    for table_name in reversed(PROJECT_SCOPED_TABLES):
        _disable_project_scoped_rls(table_name)

    op.drop_index("ix_field_frequency_distribution_field_profile_id", table_name="field_frequency_distribution")
    op.drop_index("ix_field_frequency_distribution_snapshot_id", table_name="field_frequency_distribution")
    op.drop_index("ix_field_frequency_distribution_project_id", table_name="field_frequency_distribution")
    op.drop_table("field_frequency_distribution")

    op.drop_index("ix_field_most_frequent_field_profile_id", table_name="field_most_frequent")
    op.drop_index("ix_field_most_frequent_snapshot_id", table_name="field_most_frequent")
    op.drop_index("ix_field_most_frequent_project_id", table_name="field_most_frequent")
    op.drop_table("field_most_frequent")

    op.drop_index("ix_field_profiles_table_profile_id", table_name="field_profiles")
    op.drop_index("ix_field_profiles_snapshot_id", table_name="field_profiles")
    op.drop_index("ix_field_profiles_project_id", table_name="field_profiles")
    op.drop_table("field_profiles")

    op.drop_index("ix_table_profiles_snapshot_id", table_name="table_profiles")
    op.drop_index("ix_table_profiles_project_id", table_name="table_profiles")
    op.drop_table("table_profiles")

    op.drop_index("ix_app_data_metadata_tables_snapshot_id", table_name="app_data_metadata_tables")
    op.drop_index("ix_app_data_metadata_tables_project_id", table_name="app_data_metadata_tables")
    op.drop_table("app_data_metadata_tables")

    op.drop_index("ix_app_data_metadata_fields_snapshot_id", table_name="app_data_metadata_fields")
    op.drop_index("ix_app_data_metadata_fields_project_id", table_name="app_data_metadata_fields")
    op.drop_table("app_data_metadata_fields")

    op.execute("DROP INDEX IF EXISTS ix_app_data_meta_app_fetch_desc")
    op.drop_index("ix_app_data_metadata_snapshot_fetched_at", table_name="app_data_metadata_snapshot")
    op.drop_index("ix_app_data_metadata_snapshot_app_id", table_name="app_data_metadata_snapshot")
    op.drop_index("ix_app_data_metadata_snapshot_project_id", table_name="app_data_metadata_snapshot")
    op.drop_table("app_data_metadata_snapshot")
