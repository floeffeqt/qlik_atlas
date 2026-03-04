---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - analytics
  - governance
  - usage
  - actions
  - frontend
  - backend
updated: 2026-03-04
owners: []
source_of_truth: no
related_specs:
  - QLIK-PS-002
  - QLIK-PS-004
  - QLIK-PS-005
  - QLIK-PS-006
related_docs:
  - docs/DB_MODEL.md
  - docs/RELEASE_NOTES/README.md
---

# Release Note: Analytics Modul 5 "Governance & Operations" live

## Datum

- 2026-03-04

## Summary

- Modul 5 wurde von `planned` auf `live` umgestellt.
- Es gibt jetzt ein dediziertes DB-first Insight fuer Governance-Signale:
  - Low/No-Usage Apps
  - Low-Signal Tabellen
  - Low-Signal Felder
  - Low-Signal QVD-Knoten
  - automatisch abgeleiteter Maßnahmenplan
- Die Umsetzung basiert auf vorhandenen Tabellen (`app_data_metadata_*`, `qlik_app_usage`, `lineage_nodes`, `lineage_edges`) ohne neue Dependencies.

## Backend

- Neue Runtime-Logik:
  - `backend/app/analytics_runtime_views.py`
  - neuer Loader: `load_governance_operations(...)`
  - inkl. Hilfslogik fuer Usage-Signal, Candidate-Selektion und Action-Plan-Bildung
- Neuer API-Endpoint:
  - `GET /api/analytics/insights/governance-ops`
  - in `backend/main.py`
- Neue Response-Modelle:
  - `backend/shared/analytics_models.py`
  - `GovernanceOperationsResponse` + Untermodelle

## Frontend

- `frontend/analytics.html`:
  - Modul-5-Kachel auf `live`
  - neue Governance-Sektion mit:
    - KPI-Overview
    - Tabellen fuer App/Table/Field/QVD Kandidaten
    - Maßnahmenplan-Panel
  - jede Abbildung enthaelt Analysebeschreibung + Datenbeschreibung
  - Reload integriert `governance-ops` Insight in den bestehenden Analytics-Load-Flow

## Tests / Verifikation

- Compile-Check erfolgreich:
  - `backend/app/analytics_runtime_views.py`
  - `backend/shared/analytics_models.py`
  - `backend/main.py`
  - `backend/tests/test_analytics_runtime_views.py`
  - `backend/tests/test_analytics_api.py`
- Tests erweitert:
  - `backend/tests/test_analytics_runtime_views.py`
    - Governance-Loader Candidate/Action-Plan
  - `backend/tests/test_analytics_api.py`
    - Endpoint-Contract + Error-Code fuer `governance-ops`
- `pytest` Lauf war in dieser Session nicht moeglich (`pytest` Modul nicht installiert).

## DB Model Hinweis

- Keine Schema-Aenderung, keine Migration.
- `docs/DB_MODEL.md` bleibt unveraendert, da nur Read-/Aggregationslogik und API/Frontend erweitert wurden.
