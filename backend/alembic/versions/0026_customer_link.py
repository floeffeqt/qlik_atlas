"""customers: add customer_link column

Revision ID: 0026_customer_link
Revises: 0025_task_times
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0026_customer_link"
down_revision = "0025_task_times"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("customer_link", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "customer_link")
