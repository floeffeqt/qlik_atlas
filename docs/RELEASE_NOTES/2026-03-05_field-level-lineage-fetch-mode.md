---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - lineage
  - field-level
  - fetch-job
  - frontend
  - backend
updated: 2026-03-05
owners: []
source_of_truth: no
related_specs:
  - QLIK-PS-002
  - QLIK-PS-004
  - QLIK-PS-006
  - QLIK-PS-009
related_docs:
  - docs/RELEASE_NOTES/README.md
  - docs/DB_MODEL.md
---

# Release Note: Field-Level Lineage Fetch Mode

## Datum

- 2026-03-05

## Summary

- Fetch-Jobs unterstuetzen jetzt einen einstellbaren Lineage-Graph-Level fuer den Step `app-edges`.
- Der Standard bleibt `resource`; optional sind `field`, `table` und `all`.
- Dadurch kann Field-Level-Lineage in den bestehenden DB-first Graph-Flow uebernommen und im Lineage-Frontend visualisiert werden.

## Backend

- `FetchJobRequest` erweitert um `lineageLevel` (`resource|field|table|all`, default `resource`).
- `fetch_app_edges_for_apps(...)` nutzt den gewaehlten Level fuer:
  - `GET /api/v1/lineage-graphs/nodes/{qri}?level=...`
- Sicherer Fallback: ungueltige Werte werden auf `resource` normalisiert.
- Fetch-Job-Result und Log enthalten den verwendeten Lineage-Level.
- QRI-Heuristik erweitert: Feldknoten werden als `type=field` erkannt (statt `other`), wenn entsprechende Hinweise vorliegen.

## Frontend

- `projects.html` Fetch-Modal erweitert um Auswahl:
  - `Resource (Standard)`, `Field`, `Table`, `All`
- Der Wert wird beim Start des Fetch-Jobs an `/api/fetch/jobs` mitgesendet.
- `lineage.html` erweitert:
  - neuer Typfilter `Field`
  - Legend-Eintrag und Farbe fuer Field-Nodes

## Datenmodell

- Keine DB-Schema-Aenderung.
- `docs/DB_MODEL.md` unveraendert, da nur Fetch-/Normalisierungs- und UI-Logik angepasst wurde.
