"""add role column to users table

Revision ID: 0004_add_user_role
Revises: 0003_customers_and_projects
Create Date: 2026-02-23 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_add_user_role'
down_revision = '0003_customers_and_projects'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('role', sa.String(20), nullable=False, server_default='user'))


def downgrade() -> None:
    op.drop_column('users', 'role')
