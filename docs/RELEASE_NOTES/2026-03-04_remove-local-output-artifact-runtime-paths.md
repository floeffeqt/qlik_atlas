---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - backend
  - db-first
  - runtime
  - artifacts
  - cleanup
updated: 2026-03-04
owners: []
source_of_truth: no
related_specs:
  - QLIK-PS-002
  - QLIK-PS-004
  - QLIK-PS-005
  - QLIK-PS-006
related_docs:
  - README.md
  - backend/README.md
  - docs/RELEASE_NOTES/README.md
---

# Release Note: Remove Local Output Artifact Runtime Paths

## Datum

- 2026-03-04

## Summary

- Runtime und Fetch-Job laufen jetzt konsequent DB-first ohne lokale `backend/output`-Artefakte.
- Legacy-Fallbacks auf lokale JSON-Artefakte wurden aus dem Backend-Runtime-Flow entfernt.
- Lokale Artefakt-Bereinigung im Fetch-Job wurde auf "skipped" umgestellt, da keine lokalen Runtime-Artefakte mehr verwendet werden.

## Backend

- `backend/main.py`:
  - Entfernt:
    - `FETCH_WRITE_LOCAL_ARTIFACTS` Runtime-Schalter
    - lokale Output-Konstanten (`APPS_INVENTORY_FILE`, `SPACES_FILE`, `TENANT_DATA_CONNECTIONS_FILE`, `LINEAGE_OUT_DIR`, `APP_EDGES_DIR`, `APP_USAGE_DIR`)
    - lokale Fallback-Leser und Scanner fuer Apps/Lineage/Usage/Scripts
    - lokale Artifact-Cleanup-Logik
  - Fetch-Steps (`apps`, `spaces`, `data-connections`, `lineage`, `app-edges`, `usage`) nutzen nur In-Memory-Payloads + DB-Persistenz.
  - DB-Store-Step nutzt keine lokalen Artefakt-Fallbacks mehr.

- `backend/shared/config.py`:
  - Entfernt ungenutzte Output-bezogene Settings (`data_dir`, `usage_dir`, `scripts_dir`, `data_connections_file`, `spaces_file`).
  - Beibehalten: `env`, `frontend_dist`, CORS-Settings, `fetch_trigger_token`.

## Dokumentation

- `README.md` und `backend/README.md` wurden auf DB-first-only Verhalten angepasst.

## Hinweise

- Diese Aenderung betrifft Runtime-/Fetch-Job-Pfade der Anwendung und die zugehoerigen Fetcher.
- Fetcher schreiben keine lokalen Output-Artefakte mehr; Verarbeitung bleibt in-memory + DB-Persistenz.
