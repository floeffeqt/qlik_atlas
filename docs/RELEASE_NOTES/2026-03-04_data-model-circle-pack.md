---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - analytics
  - data-model
  - d3
  - circle-pack
  - frontend
  - backend
updated: 2026-03-04
owners: []
source_of_truth: no
related_specs:
  - QLIK-PS-002
  - QLIK-PS-004
  - QLIK-PS-006
related_docs:
  - docs/DB_MODEL.md
  - docs/RELEASE_NOTES/README.md
---

# Release Note: Data Model Circle Pack (Area -> App)

## Datum

- 2026-03-04

## Summary

- Im Analytics Modul 3 (Data Model) wurde eine neue D3 Visualisierung hinzugefuegt: Zoomable Circle Packing mit Hierarchie `Bereich -> App`.
- Kreisgroessen sind relativ auf der jeweiligen Ebene.
- Die Datenbasis ist Analytics (latest Snapshot je App), nicht Lineage.

## Backend

- Neuer Endpoint:
  - `GET /api/analytics/insights/data-model-pack`
- Query Parameter:
  - `project_id` (optional)
  - `metric` (`static_byte_size_latest|complexity_latest`)
- Neue Response-Modelle fuer Data-Model-Pack in `shared/analytics_models.py`.
- Neue Runtime-Loader-Funktion in `app/analytics_runtime_views.py`:
  - `load_data_model_pack(...)`

## Frontend

- `frontend/analytics.html` wurde im Modul 3 um eine Circle-Pack-Section erweitert:
  - Metrik-Select (v1: Static Byte Size, Complexity)
  - Breadcrumb Navigation
  - Zoom/Drilldown auf Bereich- und App-Ebene
- Metrikwechsel laedt nur die Circle-Pack-Daten neu.
- Volles Reload laedt jetzt zusaetzlich den neuen Data-Model-Pack Payload.

## Tests

- API Contract Tests erweitert:
  - Erfolgsfall fuer neuen Endpoint
  - Fehler-Mapping auf `analytics_data_model_pack_query_failed`
  - 422 fuer ungueltige `metric`
- Runtime Unit Tests erweitert:
  - Aggregation und Sortierung Bereich/App
  - Metrikpfade `static_byte_size_latest` und `complexity_latest`

