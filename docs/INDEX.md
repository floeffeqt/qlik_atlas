---
doc_type: reference
scope: project
project_key: qlik_atlas
status: active
tags:
  - docs-index
  - project-context
  - status
  - requirements
updated: 2026-02-25
owners: []
source_of_truth: yes
related_specs:
  - QLIK-PS-002
related_docs:
  - docs/CONTEXT.md
  - REQUIREMENTS.md
  - PROJECT_STATUS.md
  - FIXES_APPLIED.md
---

# Documentation Index

## Purpose

- Primarer Einstiegspunkt fuer Menschen und LLMs zum Projektkontext von `qlik_atlas`.
- Definiert, welche Dokumente zuerst gelesen werden sollen.

## Current State

- Das Projekt nutzt weiterhin Root-Dokumente (`REQUIREMENTS.md`, `PROJECT_STATUS.md`, `FIXES_APPLIED.md`).
- `docs/` wurde als strukturierter Einstieg fuer Doku-Scan und kuenftige Projektdokumentation eingefuehrt.
- User-facing Read-Pfade fuer Graph/Inventory/Spaces/Data Connections/Usage/Script werden auf DB-only Runtime-Reads migriert; `GraphStore` wurde als Runtime-Komponente entfernt.

## Read First (Agent Session / Kontextaufbau)

- `CONTEXT.md` (project-context, Einstieg / Grenzen / wichtige Hinweise)
- `../PROJECT_STATUS.md` (aktueller Umsetzungsstand)
- `../REQUIREMENTS.md` (Roadmap / Anforderungen)
- `../FIXES_APPLIED.md` (historische Fixes / bekannte Ursachen)

## Project Docs

- `CONTEXT.md` (projektbezogener Kontext und Doku-Nutzung)
- `RELEASE_NOTES/README.md` (Struktur fuer kuenftige Release Notes im `docs`-Bereich)
- `RELEASE_NOTES/2026-02-25_db-only-runtime-reads-and-graphstore-removal.md` (DB-only Runtime-Reads + GraphStore-Entfernung)

## Open Questions / Risks

- Root-Dokumente sind teils historisch gewachsen; Struktur/Metadaten sind noch nicht vereinheitlicht.
- Einige Dateien enthalten Zeichenkodierungsartefakte und sollten spaeter bereinigt werden (ohne Inhalt zu verlieren).

## References

- `../AGENTS.md`
- `../.product-specs/spec-index.md`
- `<KI_ROOT>\\documentation\\POLICY\\scan-order.md` (zentrale Scan-Reihenfolge; ueber private Bridge referenziert)

