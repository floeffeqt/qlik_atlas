"""drop legacy qlik_credentials table (superseded by encrypted customer credentials)

Revision ID: 0008_drop_legacy_qlik_creds
Revises: 0007_db_runtime_source_tables
Create Date: 2026-02-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_drop_legacy_qlik_creds"
down_revision = "0007_db_runtime_source_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy table from early design; credentials are stored encrypted in public.customers.
    op.execute("DROP TABLE IF EXISTS public.qlik_credentials")


def downgrade() -> None:
    op.create_table(
        "qlik_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_url", sa.String(length=500), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
