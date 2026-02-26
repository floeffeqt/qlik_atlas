---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - lineage
  - frontend
  - backend
  - qlik-spaces
  - migration
updated: 2026-02-25
owners: []
source_of_truth: no
related_specs:
  - PS-003
  - PS-004
  - PS-005
  - QLIK-PS-002
  - QLIK-PS-004
related_docs:
  - frontend/lineage.html
  - backend/app/db_runtime_views.py
  - backend/alembic/versions/0009_expand_qlik_spaces_columns_from_jsonb.py
---

# Lineage Filters: App Names + Space Names, and Materialized `qlik_spaces` Columns

## Summary

- App-Filter in der Lineage-UI zeigt jetzt App-Namen (mit App-ID als Zuordnung)
- Bereichsfilter nutzt DB-angereicherte `spaceName`-Werte aus `qlik_spaces`
- Graph-Nodes werden beim DB-Read mit `appName`/`spaceName` aus `qlik_apps` + `qlik_spaces` angereichert
- `qlik_spaces` erhaelt materialisierte Spalten fuer wichtige JSONB-Felder (`type`, `ownerID`, `spaceID`, `tenantID`, `createdAt`, `spaceName`, `updatedAt`)
- UI-Node-Formen wurden wieder auf Kreise zurueckgestellt

## Notes

- Die Datenquelle fuer die Lineage-UI bleibt DB-basiert (kein Rueckfall auf lokale Runtime-Artefakte).
- Die neue Migration `0009` backfilled vorhandene `qlik_spaces.data` JSONB-Werte in die neuen Spalten.
