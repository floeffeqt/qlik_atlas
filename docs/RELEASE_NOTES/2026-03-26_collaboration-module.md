# Release: Project Collaboration Module (2026-03-26)

## Summary

Vollstaendiges Collaboration-Modul fuer projekt- und app-uebergreifende Zusammenarbeit:
Tasks, Tags, Dokumentation, Lineage-Kommentare, App-READMEs, Dashboard-Metriken.

## Database (Migration 0021 + Patch 0022)

- 7 neue Tabellen: `tasks`, `tags`, `task_tags`, `doc_entries`, `node_comments`, `app_readmes`, `doc_templates`
- RLS Policies fuer 4 project-scoped Tabellen
- Trigger `set_updated_at()` fuer automatische Timestamp-Updates
- 8 globale Default-Templates geseeded
- Patch-Migration 0022: Idempotente Drift-Korrektur (`parent_task_id`, `priority`, `readme_type`, `comment_type`, partielle Unique-Indexes)

## Backend (backend/app/collab/)

25 neue API-Endpunkte. `project_id` ist optional in Metrics, Tasks, Log Entries und Apps-ohne-README — ohne Filter werden alle Projekte des Users aggregiert (RLS-gefiltert). Responses enthalten `project_name`/`customer_name` im General-Mode:

| Bereich | Endpunkte |
|---|---|
| Tags | `GET/POST /api/tags`, `PUT/DELETE /api/tags/{tag_id}` |
| Tasks | `GET/POST /api/tasks`, `GET/PUT /api/tasks/{task_id}` |
| Task-Tags | `POST /api/task-tags`, `DELETE /api/task-tags/{task_id}/{tag_id}` |
| Log Entries | `GET/POST /api/log-entries`, `GET /api/log-entries/{entry_id}` (offset-Pagination) |
| Node Comments | `GET /api/node-comments`, `GET /api/node-comments/counts`, `POST /api/node-comments` |
| Readmes | `GET/POST /api/readmes`, `PUT /api/readmes/{readme_id}` |
| Templates | `GET /api/templates?type=` |
| Dashboard | `GET /api/dashboard/metrics` |
| Apps ohne README | `GET /api/apps/without-readme` † |
| App Health | `GET /api/apps/health` † (README-Status, Tasks, letzter Log pro App) |
| Qlik Apps Lookup | `GET /api/qlik-apps`, `GET /api/qlik-apps/{app_id}` |
| Projekt-Mitglieder | `GET /api/projects/{project_id}/members` |

## Rename: Doku → Log

- API-Pfade umbenannt: `/api/doc-entries` → `/api/log-entries`
- Schema-Klassen: `DocEntryIn/Out` → `LogEntryIn/Out`
- Dashboard-Metriken: `doc_entries` → `log_entries`, `doc_entries_this_week` → `log_entries_this_week`
- UI-Labels: "Doku-Eintrag" → "Log-Eintrag", "Änderungslog" → "Logs"
- DB-Tabelle `doc_entries` und SQLAlchemy-Model `DocEntry` bewusst unveraendert (keine Migration noetig)

## Frontend

- **Dashboard** (`index.html`): **General/Projekt Toggle** (Pill-Switch), 4-Metriken Stats-Grid, **App-Uebersicht** (Health-Tabelle: README-Status, offene/erledigte Tasks, letzter Log pro App), Task-Listen mit Detail-Popup, Log Feed (Timeline mit Pagination), Collapsible "Apps ohne README" (max 5), Modals mit Markdown-Editor. General-Ansicht zeigt Kunde/Projekt-Badges und aggregiert ueber alle Projekte
- **App-Detail** (`app-detail.html`): 3 Tabs (Tasks, Logs, README mit Split-View Editor + **Datenquellen-Chips** aus Lineage-Graph: Downstream-Nodes als togglebare Chips, Alle-auswaehlen, Markdown-Tabellen-Injection)
- **Projekte** (`projects.html`): Main-Projekt README mit Template-Loading, Auto-Save, Anchor-Navigation
- **Lineage** (`lineage.html`): Node-Kommentar Badges, Slide-in Panel, Filter, Inline-Formular
- **Shared Module** (`assets/markdownEditor.js`): Wiederverwendbarer Split-View Markdown Editor

## Spec Compliance

- QLIK-PS-003: RLS auf allen project-scoped Tabellen
- QLIK-PS-008: Migrationsname `0021_project_collab.py` (23 Zeichen, Limit 30)

## Changed Files

- `backend/alembic/versions/0021_project_collab.py` (Basis-Migration)
- `backend/alembic/versions/0022_collab_patch.py` (Drift-Korrektur)
- `backend/app/models.py`
- `backend/app/collab/__init__.py`, `schemas.py`, `routes.py`
- `backend/main.py`
- `frontend/index.html`, `app-detail.html`, `projects.html`, `lineage.html`
- `frontend/assets/markdownEditor.js`
- `docs/DB_MODEL.md`, `docs/CONTEXT.md`, `PROJECT_STATUS.md`
