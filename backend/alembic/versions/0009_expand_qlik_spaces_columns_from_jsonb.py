"""expand qlik_spaces with materialized columns from JSONB payload

Revision ID: 0009_expand_qlik_spaces_cols
Revises: 0008_drop_legacy_qlik_creds
Create Date: 2026-02-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_expand_qlik_spaces_cols"
down_revision = "0008_drop_legacy_qlik_creds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("qlik_spaces", sa.Column("type", sa.String(length=100), nullable=True))
    op.add_column("qlik_spaces", sa.Column("ownerId", sa.String(length=255), nullable=True))
    op.add_column("qlik_spaces", sa.Column("spaceId", sa.String(length=100), nullable=True))
    op.add_column("qlik_spaces", sa.Column("tenantId", sa.String(length=100), nullable=True))
    op.add_column("qlik_spaces", sa.Column("createdAt", sa.Text(), nullable=True))
    op.add_column("qlik_spaces", sa.Column("spaceName", sa.String(length=255), nullable=True))
    op.add_column("qlik_spaces", sa.Column("updatedAt", sa.Text(), nullable=True))

    op.create_index("ix_qlik_spaces_spaceId", "qlik_spaces", ["spaceId"])
    op.create_index("ix_qlik_spaces_spaceName", "qlik_spaces", ["spaceName"])

    op.execute(
        """
        UPDATE public.qlik_spaces
        SET
            "type" = COALESCE("type", data->>'type'),
            "ownerId" = COALESCE("ownerId", data->>'ownerId', data->>'ownerID'),
            "spaceId" = COALESCE("spaceId", data->>'spaceId', data->>'spaceID', data->>'id'),
            "tenantId" = COALESCE("tenantId", data->>'tenantId', data->>'tenantID'),
            "createdAt" = COALESCE("createdAt", data->>'createdAt'),
            "spaceName" = COALESCE("spaceName", data->>'spaceName', data->>'spacename', data->>'name'),
            "updatedAt" = COALESCE("updatedAt", data->>'updatedAt')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_qlik_spaces_spaceName", table_name="qlik_spaces")
    op.drop_index("ix_qlik_spaces_spaceId", table_name="qlik_spaces")
    op.drop_column("qlik_spaces", "updatedAt")
    op.drop_column("qlik_spaces", "spaceName")
    op.drop_column("qlik_spaces", "createdAt")
    op.drop_column("qlik_spaces", "tenantId")
    op.drop_column("qlik_spaces", "spaceId")
    op.drop_column("qlik_spaces", "ownerId")
    op.drop_column("qlik_spaces", "type")
