"""doc_entries: add warum and betrifft columns

Revision ID: 0023_doc_entries_fields
Revises: 0022_collab_patch
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_doc_entries_fields"
down_revision = "0022_collab_patch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("doc_entries", sa.Column("warum",    sa.Text(), nullable=True))
    op.add_column("doc_entries", sa.Column("betrifft", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("doc_entries", "betrifft")
    op.drop_column("doc_entries", "warum")
