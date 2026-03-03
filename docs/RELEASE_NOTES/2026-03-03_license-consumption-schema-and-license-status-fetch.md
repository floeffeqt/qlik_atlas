---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - fetch-job
  - qlik-cloud
  - licenses
  - backend
updated: 2026-03-03
owners: []
source_of_truth: no
related_specs:
  - QLIK-PS-007
related_docs:
  - docs/DB_MODEL.md
  - docs/RELEASE_NOTES/README.md
---

# Release Note: License Consumption Schema + License Status Fetch

## Datum

- 2026-03-03

## Anpassungen

- `licenses/consumption` wurde auf das angeforderte Response-Schema ausgerichtet.
- Neues Fetch-Modul fuer `/api/v1/licenses/status` wurde implementiert und in den Fetch-Job integriert.

## Backend

- Neuer Fetcher:
  - `backend/fetchers/fetch_licenses_status.py`
- `backend/fetchers/fetch_licenses_consumption.py` normalisiert jetzt:
  - `id`, `appId`, `userId`, `endTime`, `duration`, `sessionId`, `allotmentId`, `minutesUsed`, `capacityUsed`, `licenseUsage`

## Fetch-Job Integration

- Neuer Step:
  - `licenses-status`
- Job-Log/Persistenzzaehler erweitert um:
  - `licenseStatus`
- Frontend-Step-Auswahl erweitert:
  - `Licenses Status`

## DB / Migration

- Neue Migration:
  - `backend/alembic/versions/0016_license_schema_status.py`
- `qlik_license_consumption` um schema-relevante Einzelspalten erweitert.
- Neue Tabelle:
  - `qlik_license_status` (project-scoped, RLS-geschuetzt)

## Hinweis

- Nach Deployment ist `alembic upgrade head` erforderlich, bevor der neue Fetch-Job Daten persistieren kann.
