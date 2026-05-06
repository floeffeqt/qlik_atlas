---
doc_type: release-notes
scope: project
project_key: qlik_atlas
status: active
tags:
  - release-notes
  - db-source-of-truth
  - runtime-reads
  - graphstore-removal
  - lineage
updated: 2026-02-25
owners: []
source_of_truth: no
related_specs:
  - PS-003
  - PS-004
  - PS-005
  - QLIK-PS-002
  - QLIK-PS-004
  - QLIK-PS-005
related_docs:
  - docs/INDEX.md
  - docs/CONTEXT.md
  - PROJECT_STATUS.md
  - FIXES_APPLIED.md
---

# DB-only Runtime Reads and GraphStore Removal

## Summary

- User-facing Read-Endpunkte fuer Graph-/Inventory-nahe Daten wurden auf DB-only Runtime-Reads (RLS-scoped) umgestellt.
- Der alte dateibasierte Runtime-`GraphStore` wurde aus dem Backend entfernt.
- Dashboard zeigt die dritte Metrik jetzt als DB-Metrik (`Apps in DB`) statt lokale Dateizaehlung.
- Fetch-Jobs laufen jetzt standardmaessig DB-first (In-Memory -> PostgreSQL) ohne lokale Fetch-Artefaktdateien im Normalfall.

## Changed

- Neue DB Runtime Read-Schicht (`backend/app/db_runtime_views.py`)
  - Inventory / Apps
  - Spaces
  - Data Connections
  - Graph App / Graph Node / Orphans
  - App Usage / App Script
- Neuer Artifact-Normalisierer fuer DB-Store-Schritt (`backend/fetchers/artifact_graph.py`)
  - ersetzt GraphStore-Nutzung im Persistenzschritt
- `backend/main.py`
  - entfernt `GraphStore`-Initialisierung und `store.load()`
  - Read-Endpunkte lesen aus PostgreSQL statt lokalen Artifacts
  - `/api/health` entkoppelt von lokalen Artifact-/GraphStore-Daten
  - Fetch-Job-Schritte schreiben standardmaessig keine lokalen JSON-Artefakte mehr (`FETCH_WRITE_LOCAL_ARTIFACTS=false` default)
  - `/api/dashboard/stats` liefert DB-Counts fuer Apps/Nodes/Edges
- `backend/app/models.py`
  - neue Tabellenmodelle fuer `qlik_spaces`, `qlik_data_connections`, `qlik_app_usage`, `qlik_app_scripts`
  - `lineage_edges.app_id` fuer app-bezogene Graph-Verknuepfung
- Alembic Migration `0007_db_runtime_source_tables.py`
  - neue Tabellen + RLS + `lineage_edges.app_id`

## Notes / Impact

- Runtime-Reads fuer die genannten Endpunkte sind DB-basiert und nicht mehr vom `GraphStore` abhaengig.
- Fetch-Pipeline ist DB-first; lokale Fetch-Artefakte sind optionaler Debug/Kompatibilitaetsmodus ueber `FETCH_WRITE_LOCAL_ARTIFACTS=true`.
- Einige lokale Dateipfade bleiben fuer Legacy-/Fallback-Kompatibilitaet im Code vorhanden, sind im neuen Standardpfad aber deaktiviert.
- Fuer vollstaendige `QLIK-PS-005`-Konformitaet bleibt als Folgeschritt die Reduktion/Entfernung lokaler Artifact-Schreibpfade im produktiven Fetch-Flow.

## Validation (high level)

- Statische Syntaxpruefung (AST) der geaenderten Python-Dateien: erfolgreich
- Code-Review der Endpunkt-Quellen und RLS-scope Dependencies durchgefuehrt
- Voller Runtime-/DB-Integrationstest in dieser Session nicht ausgefuehrt (lokale Python-Dependencies im Host-Interpreter fehlten)
