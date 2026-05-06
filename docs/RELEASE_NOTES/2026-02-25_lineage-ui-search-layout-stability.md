---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - frontend
  - lineage
  - ux
  - d3
updated: 2026-02-25
owners: []
source_of_truth: no
related_specs:
  - PS-003
  - PS-004
related_docs:
  - README.md
  - docs/RELEASE_NOTES/README.md
---

# Lineage UI: Search, Layout Persistence, and Interaction Stability

## Summary

- Erweiterte Filter/Suche in `lineage.html` (Typ, App, Bereich/Layer, Freitext)
- D3-Graph-Interaktion stabilisiert (kein unerwartetes Auto-Fit nach Node-Drag)
- Node-Positionen sind nun verschiebbar und bleiben per `localStorage` gespeichert (pro Projektansicht)
- Node-Typen haben neben Farben auch unterschiedliche Symbole (D3 symbols)

## Notes

- Graph-Library ist weiterhin `D3.js` (kein Cytoscape / React Flow)
- `Layout Reset` entfernt gespeicherte Positionen fuer die aktuelle Projekt-/All-Ansicht
- Runtime-Datenquelle bleibt DB-basiert (nur UI-Interaktion angepasst)
