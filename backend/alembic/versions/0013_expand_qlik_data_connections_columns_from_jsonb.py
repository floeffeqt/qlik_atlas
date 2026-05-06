"""expand qlik_data_connections with materialized columns from JSONB payload

Revision ID: 0013_qdc_cols
Revises: 0012_fix_qlik_spaces_cols
Create Date: 2026-02-27 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0013_qdc_cols"
down_revision = "0012_fix_qlik_spaces_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("qlik_data_connections", sa.Column("id", sa.String(length=120), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("qID", sa.String(length=120), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("qri", sa.Text(), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("tags", JSONB(), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("user", sa.String(length=255), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("links", JSONB(), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("qName", sa.String(length=255), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("qType", sa.String(length=120), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("space", sa.String(length=100), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("qLogOn", sa.Boolean(), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("tenant", sa.String(length=100), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("created", sa.Text(), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("updated", sa.Text(), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("version", sa.String(length=100), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("privileges", JSONB(), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("datasourceID", sa.String(length=255), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("qArchitecture", JSONB(), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("qCredentialsID", sa.String(length=255), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("qEngineObjectID", sa.String(length=255), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("qConnectStatement", sa.Text(), nullable=True))
    op.add_column("qlik_data_connections", sa.Column("qSeparateCredentials", sa.Boolean(), nullable=True))

    op.create_index("ix_qlik_data_connections_qName", "qlik_data_connections", ["qName"])
    op.create_index("ix_qlik_data_connections_space", "qlik_data_connections", ["space"])

    op.execute(
        """
        UPDATE public.qlik_data_connections
        SET
            "id" = COALESCE("id", data->>'id', connection_id),
            "qID" = COALESCE("qID", data->>'qID'),
            "qri" = COALESCE("qri", data->>'qri'),
            "tags" = COALESCE("tags", data->'tags'),
            "user" = COALESCE("user", data->>'user'),
            "links" = COALESCE("links", data->'links'),
            "qName" = COALESCE("qName", data->>'qName', data->>'name'),
            "qType" = COALESCE("qType", data->>'qType', data->>'type'),
            "space" = COALESCE("space", data->>'space', space_id),
            "qLogOn" = COALESCE(
                "qLogOn",
                CASE
                    WHEN lower(trim(COALESCE(data->>'qLogOn', ''))) IN ('true', 't', '1', 'yes', 'y', 'on') THEN TRUE
                    WHEN lower(trim(COALESCE(data->>'qLogOn', ''))) IN ('false', 'f', '0', 'no', 'n', 'off') THEN FALSE
                    ELSE NULL
                END
            ),
            "tenant" = COALESCE("tenant", data->>'tenant'),
            "created" = COALESCE("created", data->>'created'),
            "updated" = COALESCE("updated", data->>'updated'),
            "version" = COALESCE("version", data->>'version'),
            "privileges" = COALESCE("privileges", data->'privileges'),
            "datasourceID" = COALESCE("datasourceID", data->>'datasourceID'),
            "qArchitecture" = COALESCE("qArchitecture", data->'qArchitecture'),
            "qCredentialsID" = COALESCE("qCredentialsID", data->>'qCredentialsID'),
            "qEngineObjectID" = COALESCE("qEngineObjectID", data->>'qEngineObjectID'),
            "qConnectStatement" = COALESCE("qConnectStatement", data->>'qConnectStatement'),
            "qSeparateCredentials" = COALESCE(
                "qSeparateCredentials",
                CASE
                    WHEN lower(trim(COALESCE(data->>'qSeparateCredentials', ''))) IN ('true', 't', '1', 'yes', 'y', 'on') THEN TRUE
                    WHEN lower(trim(COALESCE(data->>'qSeparateCredentials', ''))) IN ('false', 'f', '0', 'no', 'n', 'off') THEN FALSE
                    ELSE NULL
                END
            )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_qlik_data_connections_space", table_name="qlik_data_connections")
    op.drop_index("ix_qlik_data_connections_qName", table_name="qlik_data_connections")
    op.drop_column("qlik_data_connections", "qSeparateCredentials")
    op.drop_column("qlik_data_connections", "qConnectStatement")
    op.drop_column("qlik_data_connections", "qEngineObjectID")
    op.drop_column("qlik_data_connections", "qCredentialsID")
    op.drop_column("qlik_data_connections", "qArchitecture")
    op.drop_column("qlik_data_connections", "datasourceID")
    op.drop_column("qlik_data_connections", "privileges")
    op.drop_column("qlik_data_connections", "version")
    op.drop_column("qlik_data_connections", "updated")
    op.drop_column("qlik_data_connections", "created")
    op.drop_column("qlik_data_connections", "tenant")
    op.drop_column("qlik_data_connections", "qLogOn")
    op.drop_column("qlik_data_connections", "space")
    op.drop_column("qlik_data_connections", "qType")
    op.drop_column("qlik_data_connections", "qName")
    op.drop_column("qlik_data_connections", "links")
    op.drop_column("qlik_data_connections", "user")
    op.drop_column("qlik_data_connections", "tags")
    op.drop_column("qlik_data_connections", "qri")
    op.drop_column("qlik_data_connections", "qID")
    op.drop_column("qlik_data_connections", "id")
