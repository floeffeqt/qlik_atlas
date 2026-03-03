---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - fetch-job
  - backend
  - frontend
  - performance
updated: 2026-03-03
owners: []
source_of_truth: no
related_specs:
  - QLIK-PS-007
related_docs:
  - docs/RELEASE_NOTES/README.md
---

# Release Note: Parallel Fetch Steps + App-Edges Fallback + Log Reopen

## Datum

- 2026-03-03

## Backend

- Unabhaengige Fetch-Steps werden jetzt parallel ausgefuehrt:
  - `spaces`, `apps`, `data-connections`, `reloads`, `audits`, `licenses-consumption`, `licenses-status`
- Neue Steuerung:
  - `FETCH_INDEPENDENT_PARALLELISM` (Default `3`)

- `app-edges` Filterung wurde robuster gemacht:
  - nutzt zuerst `lineageSuccess` aus Runtime
  - nutzt alternativ erfolgreiche Runtime-Lineage-Payloads
  - faellt bei fehlenden Markern auf alle Apps zurueck (`fallback_all_apps`)

## Frontend

- Recent-Fetch-Logs bleiben auch bei offenem Log-Popup verfuegbar.
- Laufende Jobs koennen jederzeit ueber die Recent-Jobs-Liste erneut geoeffnet werden.

## Verifikation

- Start eines Fetch-Jobs mit mehreren unabhaengigen Steps zeigt Parallel-Ausfuehrung im Job-Log.
- Bei offenem Log-Popup kann ueber `FETCH LOG` ein laufender anderer Job geoeffnet werden.
