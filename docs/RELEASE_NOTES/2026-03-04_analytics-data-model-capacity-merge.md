---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - analytics
  - frontend
  - data-model
  - capacity
  - merge
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

# Release Note: Analytics Merge "Data Model & Capacity"

## Datum

- 2026-03-04

## Summary

- Das fruehere Modul "Performance Capacity" wurde schlank in das bestehende Data-Model-Modul integriert.
- Die Modul-2-Kachel wurde entfernt; stattdessen gibt es ein kombiniertes Modul "Data Model & Capacity".
- Es wurden keine neuen Backend-Endpunkte und keine DB-Schema-Aenderungen eingefuehrt.

## Frontend

- `frontend/analytics.html`:
  - Modulstruktur von 6 auf 5 sichtbare Module reduziert.
  - Legacy-URL-Alias hinzugefuegt: `module=performance-capacity` wird auf `module=data-model` normalisiert.
  - Data-Model-Bereich erweitert um Capacity-KPI-Snapshot:
    - Capacity Footprint (Summe `static_byte_size_latest`)
    - Peak RAM App (`reload_meta_peak_memory_bytes_latest`)
    - Peak CPU App (`reload_meta_cpu_time_spent_ms_latest`)
    - Avg Efficiency (Mittelwert `efficiency_score`)
    - High-Cost-Low-Value Count (`cost-value.summary.high_cost_low_value_count`)
    - Schema Drift Pressure (`schema_drift_apps_count / apps_count`)
  - Neues Panel "Selected App Capacity Deep Dive" mit on-demand Trendabfrage:
    - Endpoint: `GET /api/analytics/apps/{app_id}/trend?project_id=...&days=...`
    - KPIs: `size_growth_pct`, `ram_spike_factor`, `cpu_spike_factor`, `schema_change_count`, `history_points`
    - Bei weniger als 2 Trendpunkten wird ein klarer Historie-Fallback angezeigt.

## Backend / DB

- Keine Aenderung an Backend-API-Vertraegen.
- Keine Migrationen, keine neuen Tabellen, keine Schema-Aenderungen.
- DB-first Verhalten bleibt unveraendert.

## Hinweis

- Deep-Dive-Fehler werden nur im Deep-Dive-Panel dargestellt; die restliche Analytics-Seite bleibt nutzbar.
