---
doc_type: reference
scope: project
project_key: qlik_atlas
status: active
tags:
  - database-model
  - schema
  - erd
  - postgres
updated: 2026-03-16
owners: []
source_of_truth: no
related_specs:
  - QLIK-PS-003
  - QLIK-PS-004
related_docs:
  - docs/INDEX.md
  - backend/app/models.py
---

# DB Model (Current Schema Overview)

## Purpose

- Uebersicht ueber das aktuelle PostgreSQL-Datenmodell von `qlik_atlas`.
- Zeigt PK/FK-Beziehungen und wichtige fachliche (nicht als FK modellierte) Joins.

## Sources (Code-First)

- Primar: `backend/app/models.py`
- Migrationen/Policies: `backend/alembic/versions/0006_user_customer_access_and_rls.py`, `backend/alembic/versions/0007_db_runtime_source_tables.py` sowie spaetere Erweiterungs-Migrationen (`0009` bis `0012`, `0019`, `0020`)

## Important Note

- Diese Doku ist eine abgeleitete Schema-Uebersicht aus Code/Migrationen, nicht ein Live-DB-Dump.
- Einige Beziehungen sind bewusst nur fachlich modelliert (z. B. Qlik-IDs in `JSONB`/payload-nahen Feldern) und nicht als PostgreSQL-FK erzwungen.

## Table Overview

| Table | Primary Key | Foreign Keys | Zweck |
|---|---|---|---|
| `users` | `id` | - | Login/Authentifizierung |
| `refresh_tokens` | `token_id` | `user_id -> users.id`, `replaced_by_token_id -> refresh_tokens.token_id` | Persistierte Refresh-Token-Rotation fuer Browser-Sessions |
| `customers` | `id` | - | Kunden/Tenants mit verschluesselten Qlik- und Git-Credentials |
| `projects` | `id` | `customer_id -> customers.id` | Projekt-Scope fuer alle Qlik-/Lineage-Daten |
| `user_customer_access` | `(user_id, customer_id)` | `user_id -> users.id`, `customer_id -> customers.id` | Kundenzugriff fuer Nicht-Admins |
| `qlik_apps` | `(project_id, app_id)` | `project_id -> projects.id` | Qlik-App-Metadaten (JSONB + materialisierte Spalten) |
| `qlik_spaces` | `(project_id, space_id)` | `project_id -> projects.id` | Qlik-Space-Metadaten (JSONB + materialisierte Spalten) |
| `qlik_data_connections` | `(project_id, connection_id)` | `project_id -> projects.id` | Qlik Data Connections (JSONB + materialisierte Spalten) |
| `qlik_app_usage` | `(project_id, app_id)` | `project_id -> projects.id` | App-Usage-Aggregate (JSONB + materialisierte Spalten) |
| `qlik_app_scripts` | `(project_id, app_id)` | `project_id -> projects.id` | App-Skripte |
| `qlik_reloads` | `(project_id, reload_id)` | `project_id -> projects.id` | Qlik Reload-Historie (JSONB + materialisierte Spalten) |
| `qlik_audits` | `(project_id, audit_id)` | `project_id -> projects.id` | Qlik Audit-Events (JSONB + materialisierte Spalten) |
| `qlik_license_consumption` | `(project_id, consumption_id)` | `project_id -> projects.id` | Qlik License-Consumption (JSONB + materialisierte Spalten) |
| `qlik_license_status` | `(project_id, status_id)` | `project_id -> projects.id` | Qlik License-Status (JSONB + materialisierte Spalten) |
| `app_data_metadata_snapshot` | `snapshot_id` | `project_id -> projects.id` | Append-only Snapshots fuer `/api/v1/apps/{appId}/data/metadata` |
| `app_data_metadata_fields` | `row_id` | `project_id -> projects.id`, `snapshot_id -> app_data_metadata_snapshot.snapshot_id` | Feld-Metadaten pro Snapshot |
| `app_data_metadata_tables` | `row_id` | `project_id -> projects.id`, `snapshot_id -> app_data_metadata_snapshot.snapshot_id` | Tabellen-Metadaten pro Snapshot |
| `table_profiles` | `table_profile_id` | `project_id -> projects.id`, `snapshot_id -> app_data_metadata_snapshot.snapshot_id` | Tabellen-Profiling pro Snapshot (nur bei profiling enabled) |
| `field_profiles` | `field_profile_id` | `project_id -> projects.id`, `snapshot_id -> app_data_metadata_snapshot.snapshot_id`, `table_profile_id -> table_profiles.table_profile_id` | Field-Profiling pro Table-Profile |
| `field_most_frequent` | `row_id` | `project_id -> projects.id`, `snapshot_id -> app_data_metadata_snapshot.snapshot_id`, `field_profile_id -> field_profiles.field_profile_id` | Most-frequent Werte pro Field-Profile |
| `field_frequency_distribution` | `row_id` | `project_id -> projects.id`, `snapshot_id -> app_data_metadata_snapshot.snapshot_id`, `field_profile_id -> field_profiles.field_profile_id` | Frequency-Distribution Bins pro Field-Profile |
| `lineage_nodes` | `(project_id, node_id)` | `project_id -> projects.id` | Graph-Nodes |
| `lineage_edges` | `(project_id, edge_id)` | `project_id -> projects.id` | Graph-Edges |
| `script_git_mappings` | `(project_id, app_id)` | `project_id -> projects.id` | Mapping: Qlik App <-> Git-Repository/Datei fuer Script-Sync |
| `script_deployments` | `id` | `project_id -> projects.id`, `triggered_by -> users.id` | Audit-Log fuer Script Sync/Publish Operationen |

## Key Design Pattern

- Fast alle fachlichen Daten sind `project_id`-scoped.
- Viele Tabellen behalten `data JSONB` als Roh-/Kompatibilitaetsfeld.
- Wichtige UI-/Join-relevante Werte werden zunehmend als eigene Spalten materialisiert.

## Materialized Payload Columns (Examples)

### `qlik_apps`

- Payload-Spalten fuer UI/Filter/Runtime-Reads:
- `appName`, `spaceId`, `status`, `fileName`, `nodesCount`, `edgesCount`, `rootNodeId`, `lineageFetched`, `lineageSuccess`
- Zusaetzliche Item-API-Spalten (aus `/api/v1/items`):
- `id`, `ownerId`, `description`, `resourceType`, `resourceId`, `thumbnail`
- `resourceAttributes_id`, `resourceAttributes_name`, `resourceAttributes_description`
- `resourceAttributes_createdDate`, `resourceAttributes_modifiedDate`, `resourceAttributes_modifiedByUserName`
- `resourceAttributes_publishTime`, `resourceAttributes_lastReloadTime`, `resourceAttributes_trashed`
- `resourceCustomAttributes_json`, `source`, `tenant`
- `data` bleibt weiterhin erhalten

### `qlik_spaces`

- Payload-Spalten fuer UI/Joins:
- `spaceName`, `spaceId`, `ownerId`, `tenantId`, `type`, `createdAt`, `updatedAt`
- `data` bleibt weiterhin erhalten

### `qlik_app_usage`

- Payload-Spalten fuer Runtime-Reads:
- `appName`, `windowDays`, `generatedAt`, `_artifactFileName`
- Flattened Usage-Felder wie `usageReloads`, `usageAppOpens`, `usageSheetViews`, `usageUniqueUsers`, `usageLastReloadAt`, `usageLastViewedAt`, `usageClassification`
- `connections` als `JSONB`
- `data` bleibt weiterhin erhalten

### `qlik_data_connections`

- Payload-Spalten fuer Runtime-Reads/Filter:
- `id`, `qID`, `qri`, `tags`, `user`, `links`, `qName`, `qType`, `space`, `qLogOn`, `tenant`, `created`, `updated`, `version`, `privileges`, `datasourceID`, `qArchitecture`, `qCredentialsID`, `qEngineObjectID`, `qConnectStatement`, `qSeparateCredentials`
- `data` bleibt weiterhin erhalten

### `qlik_reloads`

- Payload-Spalten fuer `/api/v1/reloads`:
- `app_id`, `log`, `type`, `status`, `userId`, `weight`, `endTime`, `partial`, `tenantId`, `errorCode`, `errorMessage`, `startTime`, `engineTime`, `creationTime`
- `createdDate`, `created_date_ts`, `modifiedDate`, `modifiedByUserName`, `ownerId`, `title`, `description`
- `logAvailable`
- `operational_id`, `operational_nextExecution`, `operational_timesExecuted`, `operational_state`, `operational_hash`
- `links_self_href`, `source`, `tenant`
- `data` bleibt weiterhin erhalten

### `qlik_audits`

- Payload-Spalten fuer `/api/v1/audits`:
- `userId`, `eventId`, `tenantId`, `eventTime`, `eventType`, `links_self_href`, `extensions_actor_sub`
- `time`, `time_ts`, `subType`, `spaceId`, `spaceType`, `category`, `type`, `actorId`, `actorType`
- `origin`, `context`, `ipAddress`, `userAgent`, `properties_appId`, `data_message`, `source`, `tenant`
- `data` bleibt weiterhin erhalten

### `qlik_license_consumption`

- Payload-Spalten fuer `/api/v1/licenses/consumption`:
- `id`, `appId`, `userId`, `endTime`, `duration`, `sessionId`, `allotmentId`, `minutesUsed`, `capacityUsed`, `licenseUsage`, `source`, `tenant`
- `data` bleibt weiterhin erhalten

### `qlik_license_status`

- Payload-Spalten fuer `/api/v1/licenses/status`:
- `type`, `trial`, `valid`, `origin`, `status`, `product`, `deactivated`, `source`, `tenant`
- `data` bleibt weiterhin erhalten

## Physical FK Relationships (Enforced by DB)

- `projects.customer_id -> customers.id`
- `refresh_tokens.user_id -> users.id`
- `refresh_tokens.replaced_by_token_id -> refresh_tokens.token_id`
- `user_customer_access.user_id -> users.id`
- `user_customer_access.customer_id -> customers.id`
- `qlik_apps.project_id -> projects.id`
- `qlik_spaces.project_id -> projects.id`
- `qlik_data_connections.project_id -> projects.id`
- `qlik_app_usage.project_id -> projects.id`
- `qlik_app_scripts.project_id -> projects.id`
- `qlik_reloads.project_id -> projects.id`
- `qlik_audits.project_id -> projects.id`
- `qlik_license_consumption.project_id -> projects.id`
- `qlik_license_status.project_id -> projects.id`
- `app_data_metadata_snapshot.project_id -> projects.id`
- `app_data_metadata_fields.project_id -> projects.id`
- `app_data_metadata_fields.snapshot_id -> app_data_metadata_snapshot.snapshot_id`
- `app_data_metadata_tables.project_id -> projects.id`
- `app_data_metadata_tables.snapshot_id -> app_data_metadata_snapshot.snapshot_id`
- `table_profiles.project_id -> projects.id`
- `table_profiles.snapshot_id -> app_data_metadata_snapshot.snapshot_id`
- `field_profiles.project_id -> projects.id`
- `field_profiles.snapshot_id -> app_data_metadata_snapshot.snapshot_id`
- `field_profiles.table_profile_id -> table_profiles.table_profile_id`
- `field_most_frequent.project_id -> projects.id`
- `field_most_frequent.snapshot_id -> app_data_metadata_snapshot.snapshot_id`
- `field_most_frequent.field_profile_id -> field_profiles.field_profile_id`
- `field_frequency_distribution.project_id -> projects.id`
- `field_frequency_distribution.snapshot_id -> app_data_metadata_snapshot.snapshot_id`
- `field_frequency_distribution.field_profile_id -> field_profiles.field_profile_id`
- `lineage_nodes.project_id -> projects.id`
- `lineage_edges.project_id -> projects.id`
- `script_git_mappings.project_id -> projects.id`
- `script_deployments.project_id -> projects.id`
- `script_deployments.triggered_by -> users.id`

## Logical Relationships (Not DB-FK Enforced)

- `qlik_apps` <-> `qlik_spaces`
- Join ueber `project_id` + App-Space-Key:
- bevorzugt `qlik_apps.spaceId` (materialisiert) mit `qlik_spaces.spaceId` (materialisiert)
- Fallback in Bestandsdaten: `qlik_apps.space_id` mit `qlik_spaces.space_id`

- `qlik_app_usage` <-> `qlik_apps`
- Join ueber `project_id` + `app_id` (gleiche Composite-Key-Form, aber kein FK auf `qlik_apps`)

- `qlik_app_scripts` <-> `qlik_apps`
- Join ueber `project_id` + `app_id` (fachlich eindeutig, nicht als FK modelliert)

- `lineage_nodes` / `lineage_edges` <-> `qlik_apps`
- App-Bezug laeuft teils ueber `app_id`-Spalten, teils ueber Metadaten/Payload IDs (z. B. Qlik-QRI-Format vs UUID)
- Backend-Runtime-Reads normalisieren diese IDs fuer UI-Anreicherung

- `script_git_mappings` <-> `qlik_apps`
- Join ueber `project_id` + `app_id` (fachlich eindeutig, nicht als FK modelliert)
- Verknuepft eine Qlik App mit einer Datei in einem Git-Repository (Repo, Branch, Pfad)

- `script_deployments` <-> `script_git_mappings`
- Logischer Bezug ueber `project_id` + `app_id` (kein FK)
- Audit-Trail fuer jede Script Sync/Publish Operation (direction, commit SHA, Hashes, Status)

## Mermaid ERD (High-Level)

```mermaid
erDiagram
    USERS ||--o{ USER_CUSTOMER_ACCESS : assigned
    CUSTOMERS ||--o{ USER_CUSTOMER_ACCESS : grants
    CUSTOMERS ||--o{ PROJECTS : owns

    PROJECTS ||--o{ QLIK_APPS : contains
    PROJECTS ||--o{ QLIK_SPACES : contains
    PROJECTS ||--o{ QLIK_DATA_CONNECTIONS : contains
    PROJECTS ||--o{ QLIK_APP_USAGE : contains
    PROJECTS ||--o{ QLIK_APP_SCRIPTS : contains
    PROJECTS ||--o{ QLIK_RELOADS : contains
    PROJECTS ||--o{ QLIK_AUDITS : contains
    PROJECTS ||--o{ QLIK_LICENSE_CONSUMPTION : contains
    PROJECTS ||--o{ QLIK_LICENSE_STATUS : contains
    PROJECTS ||--o{ LINEAGE_NODES : contains
    PROJECTS ||--o{ LINEAGE_EDGES : contains
    PROJECTS ||--o{ SCRIPT_GIT_MAPPINGS : contains
    PROJECTS ||--o{ SCRIPT_DEPLOYMENTS : contains

    QLIK_SPACES ||--o{ QLIK_APPS : "logical via project_id + spaceId"
    QLIK_APPS ||--|| QLIK_APP_USAGE : "logical via (project_id, app_id)"
    QLIK_APPS ||--|| QLIK_APP_SCRIPTS : "logical via (project_id, app_id)"
    QLIK_APPS ||--o| SCRIPT_GIT_MAPPINGS : "logical via (project_id, app_id)"
    USERS ||--o{ SCRIPT_DEPLOYMENTS : triggers
```

### `customers` (Git-Integration, ab Migration 0020)

- Neue Spalten fuer Git-Anbindung pro Kunde:
- `git_provider` (String, nullable): `'github'` oder `'gitlab'`
- `git_token` (Text, nullable): AES-256-GCM verschluesselt (gleiche Crypto wie `api_key`)
- `git_base_url` (String, nullable): Custom-URL fuer Self-hosted Instanzen

### `script_git_mappings` (ab Migration 0020)

- Mapping-Spalten: `repo_identifier`, `branch`, `file_path`
- Caching-Spalten: `last_git_commit_sha`, `last_git_script_hash`, `last_qlik_script_hash`, `last_checked_at`
- Timestamps: `created_at`, `updated_at`

### `script_deployments` (ab Migration 0020)

- Audit-Spalten: `direction` (`git_to_qlik` | `qlik_to_git`), `git_commit_sha`, `git_script_hash`, `qlik_script_hash`
- Status: `status` (`success` | `failed` | `conflict`)
- Tracking: `triggered_by` (FK -> users.id), `version_message`, `error_detail`

## RLS / Access Notes

- RLS ist ein zentraler Bestandteil des Datenmodells fuer projekt-/kundenbezogene Sichtbarkeit.
- Relevante Tabellen wurden ueber Migrationen mit Policies versehen (u. a. `customers`, `projects`, `qlik_apps`, `lineage_nodes`, `lineage_edges` sowie Runtime-Tabellen aus `0007`).
- Migration `0019`: Korrektur aller 17 project-scoped `_project_inherited_select` Policies mit `app_has_customer_access()` Check.
- Migration `0020`: RLS Policies fuer `script_git_mappings` und `script_deployments` (gleicher Pattern: admin OR customer access).
- Fuer UI/Runtime-Reads ist deshalb nicht nur das Schema, sondern auch der gesetzte DB-Context (User/Rolle) relevant.

## Where To Inspect Live Schema (Without Data)

- `pgAdmin` (Service im `docker-compose.yml`)
- `information_schema.columns`
- `psql \d+ <table>`

## Runtime Analytics API (DB-First, No Schema Change)

- Neue Read-Endpunkte (rein DB-basiert, keine Lineage-Abhaengigkeit in v1-KPIs):
- `GET /api/analytics/areas`
- `GET /api/analytics/areas/{area_key}/apps`
- `GET /api/analytics/apps/{app_id}/fields`
- `GET /api/analytics/apps/{app_id}/trend`
- `GET /api/analytics/insights/cost-value`
- `GET /api/analytics/insights/bloat`
- `GET /api/analytics/insights/data-model-pack`
- `GET /api/analytics/insights/lineage-criticality`

- Bereichsdefinition fuer Analytics v1:
- `Qlik Space` ueber logischen Join `qlik_apps(project_id, space_id) -> qlik_spaces(project_id, space_id)`
- Fallback ohne Space-Mapping: `unassigned`

- Snapshot-Logik:
- Default-Sicht basiert auf latest Snapshot pro App aus `app_data_metadata_snapshot`
- Trend-Fenster basiert auf `fetched_at` und `days`-Parameter

## Script Sync API (Git-Integration, ab Migration 0020)

- Admin-only REST-Endpunkte unter `/api/script-sync/`:
- `GET /api/script-sync/mappings?project_id=` (alle Mappings eines Projekts)
- `POST /api/script-sync/mappings` (neues App-Repo Mapping)
- `PUT /api/script-sync/mappings/{app_id}` (Mapping bearbeiten)
- `DELETE /api/script-sync/mappings/{app_id}` (Mapping entfernen)
- `GET /api/script-sync/status/{app_id}?project_id=` (Drift-Status einer App)
- `GET /api/script-sync/overview?project_id=` (Sync-Status aller gemappten Apps)
- `GET /api/script-sync/history/{app_id}?project_id=` (Deployment-Audit-Log)
- `GET /api/script-sync/verify-access?project_id=&repo_identifier=` (Git-Zugang testen)

- Git-Provider-Abstraction:
- `GitProvider` ABC mit Implementierungen fuer GitHub (REST API v3) und GitLab (REST API v4)
- Factory: `build_provider()` erzeugt Provider basierend auf `customers.git_provider`
- Script-Normalisierung: BOM-Entfernung, CRLF->LF, Trailing-Whitespace-Trim vor SHA-256 Hash

- Drift Detection (Phase 1):
- Status-Endpoint und Overview-Endpoint liefern zusaetzlich `app_name`, `repo_identifier`, `branch`, `file_path`
- Drift-Logik: vergleicht normalisierte SHA-256 Hashes von Git-Skript vs Qlik-Skript (aus `qlik_app_scripts`)
- Status-Werte: `in_sync`, `git_ahead`, `qlik_ahead`, `diverged`, `error`, `unmapped`
- Cache-Spalten in `script_git_mappings` werden bei jedem Check aktualisiert

- Frontend: `script-sync.html` (Admin-Seite)
- Mapping-CRUD, Drift-Check, Stats-Karten, Deployment-History
- Projekt/Kunden-Selektion ueber globale Focus-Selectors
