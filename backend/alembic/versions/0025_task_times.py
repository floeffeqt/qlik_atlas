"""tasks: add start_time and end_time columns

Revision ID: 0025_task_times
Revises: 0024_task_start_date
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0025_task_times"
down_revision = "0024_task_start_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("start_time", sa.Time(), nullable=True))
    op.add_column("tasks", sa.Column("end_time",   sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "end_time")
    op.drop_column("tasks", "start_time")
