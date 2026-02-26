"""expand qlik_apps with materialized columns from JSONB payload

Revision ID: 0010_expand_qlik_apps_cols
Revises: 0009_expand_qlik_spaces_cols
Create Date: 2026-02-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_expand_qlik_apps_cols"
down_revision = "0009_expand_qlik_spaces_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `fetched_at` already exists on qlik_apps and is reused as the materialized fetched timestamp.
    op.add_column("qlik_apps", sa.Column("name", sa.String(length=255), nullable=True))
    op.add_column("qlik_apps", sa.Column("appId", sa.String(length=100), nullable=True))
    op.add_column("qlik_apps", sa.Column("status", sa.Integer(), nullable=True))
    op.add_column("qlik_apps", sa.Column("appName", sa.String(length=255), nullable=True))
    op.add_column("qlik_apps", sa.Column("spaceId", sa.String(length=100), nullable=True))
    op.add_column("qlik_apps", sa.Column("fileName", sa.String(length=512), nullable=True))
    op.add_column("qlik_apps", sa.Column("itemType", sa.String(length=100), nullable=True))
    op.add_column("qlik_apps", sa.Column("edgesCount", sa.Integer(), nullable=True))
    op.add_column("qlik_apps", sa.Column("nodesCount", sa.Integer(), nullable=True))
    op.add_column("qlik_apps", sa.Column("rootNodeId", sa.Text(), nullable=True))
    op.add_column("qlik_apps", sa.Column("lineageFetched", sa.Boolean(), nullable=True))
    op.add_column("qlik_apps", sa.Column("lineageSuccess", sa.Boolean(), nullable=True))

    op.create_index("ix_qlik_apps_appName", "qlik_apps", ["appName"])

    op.execute(
        """
        UPDATE public.qlik_apps
        SET
            "name" = COALESCE("name", data->>'name'),
            "appId" = COALESCE("appId", data->>'appId', app_id),
            "status" = COALESCE("status", NULLIF(data->>'status', '')::integer),
            "appName" = COALESCE("appName", data->>'appName', data->>'name'),
            "spaceId" = COALESCE("spaceId", data->>'spaceId', space_id),
            "fileName" = COALESCE("fileName", data->>'fileName'),
            "itemType" = COALESCE("itemType", data->>'itemType'),
            "edgesCount" = COALESCE("edgesCount", NULLIF(data->>'edgesCount', '')::integer),
            "nodesCount" = COALESCE("nodesCount", NULLIF(data->>'nodesCount', '')::integer),
            "rootNodeId" = COALESCE("rootNodeId", data->>'rootNodeId'),
            "lineageFetched" = COALESCE("lineageFetched", NULLIF(data->>'lineageFetched', '')::boolean),
            "lineageSuccess" = COALESCE("lineageSuccess", NULLIF(data->>'lineageSuccess', '')::boolean)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_qlik_apps_appName", table_name="qlik_apps")
    op.drop_column("qlik_apps", "lineageSuccess")
    op.drop_column("qlik_apps", "lineageFetched")
    op.drop_column("qlik_apps", "rootNodeId")
    op.drop_column("qlik_apps", "nodesCount")
    op.drop_column("qlik_apps", "edgesCount")
    op.drop_column("qlik_apps", "itemType")
    op.drop_column("qlik_apps", "fileName")
    op.drop_column("qlik_apps", "spaceId")
    op.drop_column("qlik_apps", "appName")
    op.drop_column("qlik_apps", "status")
    op.drop_column("qlik_apps", "appId")
    op.drop_column("qlik_apps", "name")
