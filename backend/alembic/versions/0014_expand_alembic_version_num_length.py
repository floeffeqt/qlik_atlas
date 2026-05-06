"""expand alembic_version.version_num length to prevent long revision id failures

Revision ID: 0014_alembic_verlen
Revises: 0013_qdc_cols
Create Date: 2026-02-27 00:00:00.000000
"""
from alembic import op


revision = "0014_alembic_verlen"
down_revision = "0013_qdc_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'alembic_version'
                  AND column_name = 'version_num'
                  AND character_maximum_length = 32
            ) THEN
                ALTER TABLE public.alembic_version
                ALTER COLUMN version_num TYPE VARCHAR(255);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'alembic_version'
                  AND column_name = 'version_num'
                  AND character_maximum_length = 255
            ) AND NOT EXISTS (
                SELECT 1
                FROM public.alembic_version
                WHERE char_length(version_num) > 32
            ) THEN
                ALTER TABLE public.alembic_version
                ALTER COLUMN version_num TYPE VARCHAR(32);
            END IF;
        END $$;
        """
    )
