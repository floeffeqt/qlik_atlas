"""add qlik credentials and lineage JSONB tables

Revision ID: 0002_qlik_and_lineage
Revises: 0001_create_users
Create Date: 2026-02-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0002_qlik_and_lineage'
down_revision = '0001_create_users'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'qlik_credentials',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_url', sa.String(500), nullable=False),
        sa.Column('api_key', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'qlik_apps',
        sa.Column('app_id', sa.String(100), primary_key=True),
        sa.Column('space_id', sa.String(100), nullable=True),
        sa.Column('data', JSONB, nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_qlik_apps_space_id', 'qlik_apps', ['space_id'])

    op.create_table(
        'lineage_nodes',
        sa.Column('node_id', sa.Text(), primary_key=True),
        sa.Column('app_id', sa.String(100), nullable=True),
        sa.Column('node_type', sa.String(50), nullable=True),
        sa.Column('data', JSONB, nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_lineage_nodes_app_id', 'lineage_nodes', ['app_id'])
    op.create_index('ix_lineage_nodes_node_type', 'lineage_nodes', ['node_type'])

    op.create_table(
        'lineage_edges',
        sa.Column('edge_id', sa.Text(), primary_key=True),
        sa.Column('source_node_id', sa.Text(), nullable=True),
        sa.Column('target_node_id', sa.Text(), nullable=True),
        sa.Column('data', JSONB, nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_lineage_edges_source', 'lineage_edges', ['source_node_id'])
    op.create_index('ix_lineage_edges_target', 'lineage_edges', ['target_node_id'])


def downgrade():
    op.drop_table('lineage_edges')
    op.drop_table('lineage_nodes')
    op.drop_table('qlik_apps')
    op.drop_table('qlik_credentials')
