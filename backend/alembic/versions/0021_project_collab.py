"""add project collaboration tables (tasks, tags, task_tags, doc_entries, node_comments, app_readmes, doc_templates)

Revision ID: 0021_project_collab
Revises: 0020_script_sync_tables
Create Date: 2026-03-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0021_project_collab"
down_revision = "0020_script_sync_tables"
branch_labels = None
depends_on = None

# Tables that receive standard project-scoped RLS policies.
RLS_PROJECT_TABLES = ["tasks", "doc_entries", "node_comments", "app_readmes"]


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # Reusable trigger function: set updated_at = now() on UPDATE        #
    # (CREATE OR REPLACE — safe if already present from a future patch)  #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE OR REPLACE FUNCTION public.set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ------------------------------------------------------------------ #
    # 1. tasks                                                           #
    # ------------------------------------------------------------------ #
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("qlik_app_id", sa.String(100), nullable=True),
        sa.Column("parent_task_id", sa.Integer, sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("assignee_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("estimated_minutes", sa.Integer, nullable=True),
        sa.Column("app_link", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_qlik_app_id", "tasks", ["qlik_app_id"])
    op.create_index("ix_tasks_parent_task_id", "tasks", ["parent_task_id"])
    op.create_index("ix_tasks_assignee_id", "tasks", ["assignee_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_priority", "tasks", ["priority"])
    op.create_index("ix_tasks_due_date", "tasks", ["due_date"])

    # ------------------------------------------------------------------ #
    # 2. tags (customer-scoped, no RLS — access via customer_id)         #
    # ------------------------------------------------------------------ #
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
    op.create_index("ix_tags_customer_id", "tags", ["customer_id"])
    op.create_index("ix_tags_name", "tags", ["name"])
    op.create_index("ix_tags_created_by", "tags", ["created_by"])

    # ------------------------------------------------------------------ #
    # 3. task_tags (join table, no RLS — inherits access via tasks)      #
    # ------------------------------------------------------------------ #
    op.create_table(
        "task_tags",
        sa.Column("task_id", sa.Integer, sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("task_id", "tag_id"),
    )
    op.create_index("ix_task_tags_task_id", "task_tags", ["task_id"])
    op.create_index("ix_task_tags_tag_id", "task_tags", ["tag_id"])

    # ------------------------------------------------------------------ #
    # 4. doc_entries                                                     #
    # ------------------------------------------------------------------ #
    op.create_table(
        "doc_entries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("qlik_app_id", sa.String(100), nullable=True),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entry_type", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("entry_date", sa.Date, nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_doc_entries_project_id", "doc_entries", ["project_id"])
    op.create_index("ix_doc_entries_qlik_app_id", "doc_entries", ["qlik_app_id"])
    op.create_index("ix_doc_entries_author_id", "doc_entries", ["author_id"])
    op.create_index("ix_doc_entries_entry_type", "doc_entries", ["entry_type"])
    op.create_index("ix_doc_entries_entry_date", "doc_entries", ["entry_date"])

    # ------------------------------------------------------------------ #
    # 5. node_comments                                                   #
    # ------------------------------------------------------------------ #
    op.create_table(
        "node_comments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lineage_node_id", sa.Text, nullable=True),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assignee_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("comment_type", sa.String(30), nullable=False, server_default="technical"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_node_comments_project_id", "node_comments", ["project_id"])
    op.create_index("ix_node_comments_lineage_node_id", "node_comments", ["lineage_node_id"])
    op.create_index("ix_node_comments_author_id", "node_comments", ["author_id"])
    op.create_index("ix_node_comments_assignee_id", "node_comments", ["assignee_id"])
    op.create_index("ix_node_comments_comment_type", "node_comments", ["comment_type"])

    # ------------------------------------------------------------------ #
    # 6. app_readmes (dual use: app README + project README)             #
    # ------------------------------------------------------------------ #
    op.create_table(
        "app_readmes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("qlik_app_id", sa.String(100), nullable=True),
        sa.Column("readme_type", sa.String(30), nullable=False, server_default="app_readme"),
        sa.Column("content_md", sa.Text, nullable=True),
        sa.Column("last_edited_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_app_readmes_project_id", "app_readmes", ["project_id"])
    op.create_index("ix_app_readmes_qlik_app_id", "app_readmes", ["qlik_app_id"])
    op.create_index("ix_app_readmes_readme_type", "app_readmes", ["readme_type"])
    op.create_index("ix_app_readmes_last_edited_by", "app_readmes", ["last_edited_by"])
    # Partial unique: one readme per app per type (when app is set)
    op.execute("""
        CREATE UNIQUE INDEX uq_app_readmes_project_app_type
        ON public.app_readmes (project_id, qlik_app_id, readme_type)
        WHERE qlik_app_id IS NOT NULL;
    """)
    # Partial unique: one readme per type without app (project-level README)
    op.execute("""
        CREATE UNIQUE INDEX uq_app_readmes_project_type
        ON public.app_readmes (project_id, readme_type)
        WHERE qlik_app_id IS NULL;
    """)

    # ------------------------------------------------------------------ #
    # 7. doc_templates                                                   #
    # ------------------------------------------------------------------ #
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
    op.create_index("ix_doc_templates_template_type", "doc_templates", ["template_type"])
    op.create_index("ix_doc_templates_project_id", "doc_templates", ["project_id"])
    # Partial unique: one override per template_type per project
    op.execute("""
        CREATE UNIQUE INDEX uq_doc_templates_type_project
        ON public.doc_templates (template_type, project_id)
        WHERE project_id IS NOT NULL;
    """)

    # ------------------------------------------------------------------ #
    # RLS policies — standard project-scoped tables                      #
    # ------------------------------------------------------------------ #
    for table_name in RLS_PROJECT_TABLES:
        policy_name = f"{table_name}_project_inherited_select"
        op.execute(f"""
            CREATE POLICY {policy_name}
            ON public.{table_name}
            FOR SELECT
            USING (
                public.app_is_admin()
                OR EXISTS (
                    SELECT 1 FROM public.projects p
                    WHERE p.id = {table_name}.project_id
                      AND public.app_has_customer_access(p.customer_id)
                )
            );
        """)
        op.execute(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE public.{table_name} FORCE ROW LEVEL SECURITY;")

    # doc_templates: global templates (project_id IS NULL) readable by all,
    # project-specific only for users with project access.
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
    # updated_at triggers                                                #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TRIGGER trg_tasks_updated_at
        BEFORE UPDATE ON public.tasks
        FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    """)
    op.execute("""
        CREATE TRIGGER trg_app_readmes_updated_at
        BEFORE UPDATE ON public.app_readmes
        FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    """)

    # ------------------------------------------------------------------ #
    # Seed global default templates                                      #
    # ------------------------------------------------------------------ #
    _seed_default_templates()


# -- helpers ----------------------------------------------------------- #

def _seed_default_templates() -> None:
    """Insert global default templates (is_default=true, project_id=NULL)."""
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


# -- downgrade -------------------------------------------------------- #

def downgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Drop triggers                                                   #
    # ------------------------------------------------------------------ #
    op.execute("DROP TRIGGER IF EXISTS trg_app_readmes_updated_at ON public.app_readmes;")
    op.execute("DROP TRIGGER IF EXISTS trg_tasks_updated_at ON public.tasks;")

    # ------------------------------------------------------------------ #
    # 2. Drop RLS policies + disable RLS                                 #
    # ------------------------------------------------------------------ #
    op.execute("DROP POLICY IF EXISTS doc_templates_project_inherited_select ON public.doc_templates;")
    op.execute("ALTER TABLE public.doc_templates DISABLE ROW LEVEL SECURITY;")

    for table_name in reversed(RLS_PROJECT_TABLES):
        policy_name = f"{table_name}_project_inherited_select"
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON public.{table_name};")
        op.execute(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY;")

    # ------------------------------------------------------------------ #
    # 3. Drop tables (respecting FK dependencies)                        #
    #    task_tags -> doc_templates -> app_readmes -> node_comments ->    #
    #    doc_entries -> tags -> tasks (last because of self-FK)           #
    # ------------------------------------------------------------------ #
    op.drop_table("task_tags")
    op.drop_table("doc_templates")
    op.drop_table("app_readmes")
    op.drop_table("node_comments")
    op.drop_table("doc_entries")
    op.drop_table("tags")
    op.drop_table("tasks")
