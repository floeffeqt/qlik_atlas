"""add missing tasks columns + create tags, task_tags, doc_templates tables

Revision ID: 0022_collab_patch
Revises: 0021_project_collab
Create Date: 2026-03-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0022_collab_patch"
down_revision = "0021_project_collab"
branch_labels = None
depends_on = None


def _col_exists(table: str, column: str) -> bool:
    """Check if a column already exists (idempotent migration support)."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
    ), {"t": table, "c": column})
    return result.scalar() is not None


def _idx_exists(index_name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"
    ), {"n": index_name})
    return result.scalar() is not None


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename=:t"
    ), {"t": table})
    return result.scalar() is not None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. tasks: add missing columns (idempotent)                         #
    # ------------------------------------------------------------------ #
    if not _col_exists("tasks", "parent_task_id"):
        op.add_column("tasks", sa.Column("parent_task_id", sa.Integer, nullable=True))
        op.create_foreign_key(
            "fk_tasks_parent_task_id",
            "tasks", "tasks",
            ["parent_task_id"], ["id"],
            ondelete="SET NULL",
        )
    if not _idx_exists("ix_tasks_parent_task_id"):
        op.create_index("ix_tasks_parent_task_id", "tasks", ["parent_task_id"])

    if not _col_exists("tasks", "priority"):
        op.add_column(
            "tasks",
            sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        )
    if not _idx_exists("ix_tasks_priority"):
        op.create_index("ix_tasks_priority", "tasks", ["priority"])
    if not _idx_exists("ix_tasks_due_date"):
        op.create_index("ix_tasks_due_date", "tasks", ["due_date"])

    # ------------------------------------------------------------------ #
    # 1b. app_readmes: add readme_type, fix qlik_app_id nullable         #
    # ------------------------------------------------------------------ #
    if not _col_exists("app_readmes", "readme_type"):
        op.add_column(
            "app_readmes",
            sa.Column("readme_type", sa.String(30), nullable=False, server_default="app_readme"),
        )
    if not _idx_exists("ix_app_readmes_readme_type"):
        op.create_index("ix_app_readmes_readme_type", "app_readmes", ["readme_type"])

    # Make qlik_app_id nullable (for project-level readmes)
    op.alter_column("app_readmes", "qlik_app_id", nullable=True)

    # Replace old plain unique constraint with partial unique indexes
    conn = op.get_bind()
    has_old_uq = conn.execute(sa.text(
        "SELECT 1 FROM pg_constraint WHERE conname='uq_app_readmes_project_app'"
    )).scalar()
    if has_old_uq:
        op.drop_constraint("uq_app_readmes_project_app", "app_readmes", type_="unique")

    if not _idx_exists("uq_app_readmes_project_app_type"):
        op.execute("""
            CREATE UNIQUE INDEX uq_app_readmes_project_app_type
            ON public.app_readmes (project_id, qlik_app_id, readme_type)
            WHERE qlik_app_id IS NOT NULL;
        """)
    if not _idx_exists("uq_app_readmes_project_type"):
        op.execute("""
            CREATE UNIQUE INDEX uq_app_readmes_project_type
            ON public.app_readmes (project_id, readme_type)
            WHERE qlik_app_id IS NULL;
        """)

    # ------------------------------------------------------------------ #
    # 1c. node_comments: add comment_type                                #
    # ------------------------------------------------------------------ #
    if not _col_exists("node_comments", "comment_type"):
        op.add_column(
            "node_comments",
            sa.Column("comment_type", sa.String(30), nullable=False, server_default="technical"),
        )
    if not _idx_exists("ix_node_comments_comment_type"):
        op.create_index("ix_node_comments_comment_type", "node_comments", ["comment_type"])

    # ------------------------------------------------------------------ #
    # 2. tags (customer-scoped, no RLS)                                  #
    # ------------------------------------------------------------------ #
    if not _table_exists("tags"):
        op.create_table(
            "tags",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(50), nullable=False),
            sa.Column("color", sa.String(7), nullable=False, server_default="#888780"),
            sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("customer_id", "name", name="uq_tags_customer_name"),
        )
        if not _idx_exists("ix_tags_customer_id"):
            op.create_index("ix_tags_customer_id", "tags", ["customer_id"])
        if not _idx_exists("ix_tags_name"):
            op.create_index("ix_tags_name", "tags", ["name"])
        if not _idx_exists("ix_tags_created_by"):
            op.create_index("ix_tags_created_by", "tags", ["created_by"])

    # ------------------------------------------------------------------ #
    # 3. task_tags (join table)                                          #
    # ------------------------------------------------------------------ #
    if not _table_exists("task_tags"):
        op.create_table(
            "task_tags",
            sa.Column("task_id", sa.Integer, sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("tag_id", sa.Integer, sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
            sa.PrimaryKeyConstraint("task_id", "tag_id"),
        )
        if not _idx_exists("ix_task_tags_task_id"):
            op.create_index("ix_task_tags_task_id", "task_tags", ["task_id"])
        if not _idx_exists("ix_task_tags_tag_id"):
            op.create_index("ix_task_tags_tag_id", "task_tags", ["tag_id"])

    # ------------------------------------------------------------------ #
    # 4. doc_templates                                                   #
    # ------------------------------------------------------------------ #
    if not _table_exists("doc_templates"):
        op.create_table(
            "doc_templates",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("template_type", sa.String(50), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("content_md", sa.Text, nullable=False),
            sa.Column("required_fields", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        if not _idx_exists("ix_doc_templates_template_type"):
            op.create_index("ix_doc_templates_template_type", "doc_templates", ["template_type"])
        if not _idx_exists("ix_doc_templates_project_id"):
            op.create_index("ix_doc_templates_project_id", "doc_templates", ["project_id"])
        if not _idx_exists("uq_doc_templates_type_project"):
            op.execute("""
                CREATE UNIQUE INDEX uq_doc_templates_type_project
                ON public.doc_templates (template_type, project_id)
                WHERE project_id IS NOT NULL;
            """)

    # ------------------------------------------------------------------ #
    # 5. RLS for doc_templates (idempotent)                              #
    # ------------------------------------------------------------------ #
    conn = op.get_bind()
    has_policy = conn.execute(sa.text(
        "SELECT 1 FROM pg_policies WHERE schemaname='public' "
        "AND tablename='doc_templates' AND policyname='doc_templates_project_inherited_select'"
    )).scalar()
    if not has_policy:
        op.execute("""
            CREATE POLICY doc_templates_project_inherited_select
            ON public.doc_templates
            FOR SELECT
            USING (
                project_id IS NULL
                OR public.app_is_admin()
                OR EXISTS (
                    SELECT 1 FROM public.projects p
                    WHERE p.id = doc_templates.project_id
                      AND public.app_has_customer_access(p.customer_id)
                )
            );
        """)
        op.execute("ALTER TABLE public.doc_templates ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE public.doc_templates FORCE ROW LEVEL SECURITY;")

    # ------------------------------------------------------------------ #
    # 6. Seed global default templates (skip if already seeded)          #
    # ------------------------------------------------------------------ #
    tpl_count = conn.execute(sa.text("SELECT count(*) FROM doc_templates")).scalar()
    if tpl_count > 0:
        return  # already seeded
    op.execute("""
        INSERT INTO doc_templates (template_type, name, content_md, required_fields, is_default)
        VALUES
        (
            'project_readme',
            'Projekt-README Vorlage',
            $tpl$## Tenant-Uebersicht
_Qlik Cloud URL, Region, Edition_

## Architektur
_QVD-Layer Struktur, Space-Struktur, Naming Conventions_

## Reload-Automation
_Tool (z.B. Qlik Application Automation), globale Zeitplaene, Zustaendiger bei Fehlern_

## Ansprechpartner
| Name | Rolle | Kontakt |
|------|-------|---------|
| | | |

## Globale Entscheidungen
_Verweis auf doc_entries (entry_type = decision) dieses Projekts_

## Bekannte Einschraenkungen
_Tenant-weite Limitierungen oder Besonderheiten_$tpl$,
            '[]'::jsonb,
            true
        ),
        (
            'app_readme',
            'App-README Vorlage',
            $tpl$## Zweck & Zielgruppe
_Was beantwortet die App? Wer nutzt sie taeglich?_

## Wichtigste KPIs
| KPI | Definition | Formel / Quelle |
|-----|-----------|-----------------|
| | | |

## Datenquellen
_QVDs, Connections, Upstream-Apps_

## Geschaeftslogik
_Set Analysis Expressions erklaert, Sonderfaelle, bewusste Ausschluesse_

## Script-Struktur
_Tabs und ihr Zweck, wichtige Variablen_

## Reload & Betrieb
_Zeitplan, Fehlerbehandlung, Ansprechpartner_

## Bekannte Einschraenkungen
_Offene Punkte, Workarounds_$tpl$,
            '[]'::jsonb,
            true
        ),
        (
            'doc_entry_change',
            'Aenderungseintrag',
            $tpl$## Was wurde geaendert?
_Kurzbeschreibung_

## Warum?
_Grund / Anforderung / Ticket-Referenz_

## Betroffene Felder / Objekte
_Liste_

## Getestet von
_Name_$tpl$,
            '[]'::jsonb,
            true
        ),
        (
            'doc_entry_decision',
            'Entscheidungseintrag',
            $tpl$## Entscheidung
_Was wurde entschieden?_

## Kontext & Begruendung
_Warum diese Entscheidung? Welche Alternativen wurden verworfen?_

## Auswirkungen
_Was aendert sich? Welche Folgeaufgaben entstehen?_

## Entschieden von
_Name(n)_$tpl$,
            '[]'::jsonb,
            true
        ),
        (
            'doc_entry_incident',
            'Incident-Eintrag',
            $tpl$## Was ist passiert?
_Beschreibung_

## Ursache
_Root Cause_

## Loesung / Workaround
_Was wurde gemacht?_

## Verhindert kuenftig durch
_Massnahmen_$tpl$,
            '[]'::jsonb,
            true
        ),
        (
            'node_comment_technical',
            'Technischer Kommentar',
            $tpl$## Technischer Hinweis
_Was ist an diesem Node bemerkenswert?_

## Abhaengigkeiten
_Welche anderen Nodes / Apps haengen davon ab?_$tpl$,
            '[]'::jsonb,
            true
        ),
        (
            'node_comment_business',
            'Business-Kommentar',
            $tpl$## Business-Kontext
_Was bedeutet dieser Node geschaeftlich?_

## Zustaendig
_Wer ist verantwortlich fuer diese Daten?_$tpl$,
            '[]'::jsonb,
            true
        ),
        (
            'node_comment_issue',
            'Issue-Kommentar',
            $tpl$## Problem
_Was stimmt hier nicht?_

## Auswirkung
_Welche Downstream-Objekte sind betroffen?_

## Zugewiesen an
_Name_$tpl$,
            '[]'::jsonb,
            true
        );
    """)


def downgrade() -> None:
    # doc_templates
    op.execute("DROP POLICY IF EXISTS doc_templates_project_inherited_select ON public.doc_templates;")
    op.execute("ALTER TABLE public.doc_templates DISABLE ROW LEVEL SECURITY;")
    op.drop_table("doc_templates")

    # task_tags
    op.drop_table("task_tags")

    # tags
    op.drop_table("tags")

    # tasks columns
    op.drop_index("ix_tasks_due_date", table_name="tasks")
    op.drop_index("ix_tasks_priority", table_name="tasks")
    op.drop_column("tasks", "priority")
    op.drop_index("ix_tasks_parent_task_id", table_name="tasks")
    op.drop_constraint("fk_tasks_parent_task_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "parent_task_id")
