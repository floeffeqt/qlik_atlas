---
doc_type: release-notes
scope: project
project_key: qlik_atlas
status: active
tags:
  - release-notes
  - index
  - changes
updated: 2026-02-25
owners: []
source_of_truth: no
related_specs: []
related_docs:
  - docs/INDEX.md
---

# Release Notes

## Purpose

- Sammelstelle fuer kuenftige Release Notes im Projekt-Dokubereich.

## Current State

- Release Notes existieren aktuell teils in Commit-Texten / Ad-hoc-Dokumenten.
- Dieser Ordner ist der neue strukturierte Ablageort fuer kuenftige Release-Zusammenfassungen.
- Erste strukturierte Architektur-Notiz erfasst die DB-only Runtime-Read-Migration und die Entfernung des dateibasierten `GraphStore`.

## Key Facts

- Empfohlene Nutzung: eine Datei pro Release/Commit-Buendel
- Inhalte kurz, pruefbar und mit Verweisen auf Specs/Testing Summaries
- Vorlage: `<KI_ROOT>\documentation\TEMPLATES\DOC_RELEASE_NOTES.md`
- Vorhandene Eintraege:
  - `2026-02-25_db-only-runtime-reads-and-graphstore-removal.md`
  - `2026-02-25_lineage-ui-search-layout-stability.md`
  - `2026-02-25_lineage-appname-space-filter-and-qlik-spaces-columns.md`
  - `2026-02-25_remove-legacy-qlik-credentials-table-plan-references.md`

## Open Questions / Risks

- Benennungskonvention fuer Release-Notizen im Projekt noch festzulegen (z. B. Datum vs. Version)

## References

- `../INDEX.md`
- `../../.product-specs/spec-index.md`
