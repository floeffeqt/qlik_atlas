"""fix qlik_spaces camelCase column names for existing DBs

Revision ID: 0012_fix_qlik_spaces_camelcase_cols
Revises: 0011_expand_qlik_app_usage_cols
Create Date: 2026-02-26 00:00:00.000000
"""
from alembic import op


revision = "0012_fix_qlik_spaces_cols"
down_revision = "0011_expand_qlik_app_usage_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing DBs may already have revision 0009 applied with legacy names:
    # ownerID / spaceID / tenantID. New code expects ownerId / spaceId / tenantId.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'qlik_spaces' AND column_name = 'ownerID'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'qlik_spaces' AND column_name = 'ownerId'
            ) THEN
                ALTER TABLE public.qlik_spaces RENAME COLUMN "ownerID" TO "ownerId";
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'qlik_spaces' AND column_name = 'spaceID'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'qlik_spaces' AND column_name = 'spaceId'
            ) THEN
                ALTER TABLE public.qlik_spaces RENAME COLUMN "spaceID" TO "spaceId";
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'qlik_spaces' AND column_name = 'tenantID'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'qlik_spaces' AND column_name = 'tenantId'
            ) THEN
                ALTER TABLE public.qlik_spaces RENAME COLUMN "tenantID" TO "tenantId";
            END IF;
        END $$;
        """
    )

    op.execute('ALTER INDEX IF EXISTS public."ix_qlik_spaces_spaceID" RENAME TO "ix_qlik_spaces_spaceId"')


def downgrade() -> None:
    op.execute('ALTER INDEX IF EXISTS public."ix_qlik_spaces_spaceId" RENAME TO "ix_qlik_spaces_spaceID"')
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'qlik_spaces' AND column_name = 'ownerId'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'qlik_spaces' AND column_name = 'ownerID'
            ) THEN
                ALTER TABLE public.qlik_spaces RENAME COLUMN "ownerId" TO "ownerID";
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'qlik_spaces' AND column_name = 'spaceId'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'qlik_spaces' AND column_name = 'spaceID'
            ) THEN
                ALTER TABLE public.qlik_spaces RENAME COLUMN "spaceId" TO "spaceID";
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'qlik_spaces' AND column_name = 'tenantId'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'qlik_spaces' AND column_name = 'tenantID'
            ) THEN
                ALTER TABLE public.qlik_spaces RENAME COLUMN "tenantId" TO "tenantID";
            END IF;
        END $$;
        """
    )
