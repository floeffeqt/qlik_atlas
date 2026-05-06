"""create required postgres extensions

Revision ID: 0000_extensions
Revises:
Create Date: 2026-01-01 00:00:00.000000
"""
from alembic import op

revision = '0000_extensions'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
