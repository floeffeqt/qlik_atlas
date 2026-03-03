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
updated: 2026-03-03
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
- Migrationen/Policies: `backend/alembic/versions/0006_user_customer_access_and_rls.py`, `backend/alembic/versions/0007_db_runtime_source_tables.py` sowie spaetere Erweiterungs-Migrationen (`0009` bis `0012`)

## Important Note

- Diese Doku ist eine abgeleitete Schema-Uebersicht aus Code/Migrationen, nicht ein Live-DB-Dump.
- Einige Beziehungen sind bewusst nur fachlich modelliert (z. B. Qlik-IDs in `JSONB`/payload-nahen Feldern) und nicht als PostgreSQL-FK erzwungen.

## Table Overview

| Table | Primary Key | Foreign Keys | Zweck |
|---|---|---|---|
| `users` | `id` | - | Login/Authentifizierung |
| `customers` | `id` | - | Kunden/Tenants mit verschluesselten Qlik-Credentials |
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
| `lineage_nodes` | `(project_id, node_id)` | `project_id -> projects.id` | Graph-Nodes |
| `lineage_edges` | `(project_id, edge_id)` | `project_id -> projects.id` | Graph-Edges |

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
- `lineage_nodes.project_id -> projects.id`
- `lineage_edges.project_id -> projects.id`

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

    QLIK_SPACES ||--o{ QLIK_APPS : "logical via project_id + spaceId"
    QLIK_APPS ||--|| QLIK_APP_USAGE : "logical via (project_id, app_id)"
    QLIK_APPS ||--|| QLIK_APP_SCRIPTS : "logical via (project_id, app_id)"
```

## RLS / Access Notes

- RLS ist ein zentraler Bestandteil des Datenmodells fuer projekt-/kundenbezogene Sichtbarkeit.
- Relevante Tabellen wurden ueber Migrationen mit Policies versehen (u. a. `customers`, `projects`, `qlik_apps`, `lineage_nodes`, `lineage_edges` sowie Runtime-Tabellen aus `0007`).
- Fuer UI/Runtime-Reads ist deshalb nicht nur das Schema, sondern auch der gesetzte DB-Context (User/Rolle) relevant.

## Where To Inspect Live Schema (Without Data)

- `pgAdmin` (Service im `docker-compose.yml`)
- `information_schema.columns`
- `psql \d+ <table>`
