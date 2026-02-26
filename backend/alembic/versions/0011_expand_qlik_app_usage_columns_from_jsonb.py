"""expand qlik_app_usage with materialized columns from JSONB payload

Revision ID: 0011_expand_qlik_app_usage_cols
Revises: 0010_expand_qlik_apps_cols
Create Date: 2026-02-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0011_expand_qlik_app_usage_cols"
down_revision = "0010_expand_qlik_apps_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("qlik_app_usage", sa.Column("appId", sa.String(length=100), nullable=True))
    op.add_column("qlik_app_usage", sa.Column("appName", sa.String(length=255), nullable=True))
    op.add_column("qlik_app_usage", sa.Column("windowDays", sa.Integer(), nullable=True))
    op.add_column("qlik_app_usage", sa.Column("usageReloads", sa.Integer(), nullable=True))
    op.add_column("qlik_app_usage", sa.Column("usageAppOpens", sa.Integer(), nullable=True))
    op.add_column("qlik_app_usage", sa.Column("usageSheetViews", sa.Integer(), nullable=True))
    op.add_column("qlik_app_usage", sa.Column("usageUniqueUsers", sa.Integer(), nullable=True))
    op.add_column("qlik_app_usage", sa.Column("usageLastReloadAt", sa.Text(), nullable=True))
    op.add_column("qlik_app_usage", sa.Column("usageLastViewedAt", sa.Text(), nullable=True))
    op.add_column("qlik_app_usage", sa.Column("usageClassification", sa.String(length=100), nullable=True))
    op.add_column("qlik_app_usage", sa.Column("connections", JSONB(), nullable=True))
    op.add_column("qlik_app_usage", sa.Column("generatedAt", sa.Text(), nullable=True))
    op.add_column("qlik_app_usage", sa.Column("_artifactFileName", sa.String(length=255), nullable=True))

    op.create_index("ix_qlik_app_usage_appName", "qlik_app_usage", ["appName"])

    op.execute(
        """
        UPDATE public.qlik_app_usage
        SET
            "appId" = COALESCE("appId", data->>'appId', app_id),
            "appName" = COALESCE("appName", data->>'appName'),
            "windowDays" = COALESCE("windowDays", NULLIF(data->>'windowDays', '')::integer),
            "usageReloads" = COALESCE("usageReloads", NULLIF(data->'usage'->>'reloads', '')::integer),
            "usageAppOpens" = COALESCE("usageAppOpens", NULLIF(data->'usage'->>'appOpens', '')::integer),
            "usageSheetViews" = COALESCE("usageSheetViews", NULLIF(data->'usage'->>'sheetViews', '')::integer),
            "usageUniqueUsers" = COALESCE("usageUniqueUsers", NULLIF(data->'usage'->>'uniqueUsers', '')::integer),
            "usageLastReloadAt" = COALESCE("usageLastReloadAt", data->'usage'->>'lastReloadAt'),
            "usageLastViewedAt" = COALESCE("usageLastViewedAt", data->'usage'->>'lastViewedAt'),
            "usageClassification" = COALESCE("usageClassification", data->'usage'->>'classification'),
            "connections" = COALESCE("connections", data->'connections'),
            "generatedAt" = COALESCE("generatedAt", data->>'generatedAt'),
            "_artifactFileName" = COALESCE("_artifactFileName", data->>'_artifactFileName')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_qlik_app_usage_appName", table_name="qlik_app_usage")
    op.drop_column("qlik_app_usage", "_artifactFileName")
    op.drop_column("qlik_app_usage", "generatedAt")
    op.drop_column("qlik_app_usage", "connections")
    op.drop_column("qlik_app_usage", "usageClassification")
    op.drop_column("qlik_app_usage", "usageLastViewedAt")
    op.drop_column("qlik_app_usage", "usageLastReloadAt")
    op.drop_column("qlik_app_usage", "usageUniqueUsers")
    op.drop_column("qlik_app_usage", "usageSheetViews")
    op.drop_column("qlik_app_usage", "usageAppOpens")
    op.drop_column("qlik_app_usage", "usageReloads")
    op.drop_column("qlik_app_usage", "windowDays")
    op.drop_column("qlik_app_usage", "appName")
    op.drop_column("qlik_app_usage", "appId")
