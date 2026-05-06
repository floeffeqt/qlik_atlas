"""tasks: add start_date column

Revision ID: 0024_task_start_date
Revises: 0023_doc_entries_fields
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_task_start_date"
down_revision = "0023_doc_entries_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("start_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "start_date")
