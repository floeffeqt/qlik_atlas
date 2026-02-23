"""add customers, projects and rebuild data tables with project scoping

Revision ID: 0003_customers_and_projects
Revises: 0002_qlik_and_lineage
Create Date: 2026-02-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0003_customers_and_projects'
down_revision = '0002_qlik_and_lineage'
branch_labels = None
depends_on = None


def upgrade():
    # ── Drop old data tables (no real data yet, rebuild with project scoping) ──
    op.drop_index('ix_lineage_edges_target', table_name='lineage_edges')
    op.drop_index('ix_lineage_edges_source', table_name='lineage_edges')
    op.drop_table('lineage_edges')

    op.drop_index('ix_lineage_nodes_node_type', table_name='lineage_nodes')
    op.drop_index('ix_lineage_nodes_app_id', table_name='lineage_nodes')
    op.drop_table('lineage_nodes')

    op.drop_index('ix_qlik_apps_space_id', table_name='qlik_apps')
    op.drop_table('qlik_apps')

    # ── Create customers ──
    op.create_table(
        'customers',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('tenant_url', sa.String(500), nullable=False),
        sa.Column('api_key', sa.Text(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Create projects ──
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_projects_customer_id', 'projects', ['customer_id'])

    # ── Recreate qlik_apps with composite PK ──
    op.create_table(
        'qlik_apps',
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('app_id', sa.String(100), nullable=False),
        sa.Column('space_id', sa.String(100), nullable=True),
        sa.Column('data', JSONB, nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('project_id', 'app_id'),
    )
    op.create_index('ix_qlik_apps_project_id', 'qlik_apps', ['project_id'])
    op.create_index('ix_qlik_apps_space_id', 'qlik_apps', ['space_id'])

    # ── Recreate lineage_nodes with composite PK ──
    op.create_table(
        'lineage_nodes',
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('node_id', sa.Text(), nullable=False),
        sa.Column('app_id', sa.String(100), nullable=True),
        sa.Column('node_type', sa.String(50), nullable=True),
        sa.Column('data', JSONB, nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('project_id', 'node_id'),
    )
    op.create_index('ix_lineage_nodes_project_id', 'lineage_nodes', ['project_id'])
    op.create_index('ix_lineage_nodes_app_id', 'lineage_nodes', ['app_id'])
    op.create_index('ix_lineage_nodes_node_type', 'lineage_nodes', ['node_type'])

    # ── Recreate lineage_edges with composite PK ──
    op.create_table(
        'lineage_edges',
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('edge_id', sa.Text(), nullable=False),
        sa.Column('source_node_id', sa.Text(), nullable=True),
        sa.Column('target_node_id', sa.Text(), nullable=True),
        sa.Column('data', JSONB, nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('project_id', 'edge_id'),
    )
    op.create_index('ix_lineage_edges_project_id', 'lineage_edges', ['project_id'])
    op.create_index('ix_lineage_edges_source', 'lineage_edges', ['source_node_id'])
    op.create_index('ix_lineage_edges_target', 'lineage_edges', ['target_node_id'])


def downgrade():
    op.drop_table('lineage_edges')
    op.drop_table('lineage_nodes')
    op.drop_table('qlik_apps')
    op.drop_table('projects')
    op.drop_table('customers')

    # Restore original qlik_apps
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
