"""prepare customer credential columns for AES-GCM envelopes

Revision ID: 0005_customer_credentials_aesgcm_storage
Revises: 0004_add_user_role
Create Date: 2026-02-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_customer_credentials_aesgcm"
down_revision = "0004_add_user_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # AES-GCM envelopes are longer than plaintext URLs; move tenant_url to TEXT.
    op.alter_column(
        "customers",
        "tenant_url",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=False,
        postgresql_using="tenant_url::text",
    )


def downgrade() -> None:
    op.alter_column(
        "customers",
        "tenant_url",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=False,
        postgresql_using="left(tenant_url, 500)",
    )
