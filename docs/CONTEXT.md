---
doc_type: project-context
scope: project
project_key: qlik_atlas
status: active
tags:
  - project-context
  - architecture
  - onboarding
  - docs
updated: 2026-02-25
owners: []
source_of_truth: yes
related_specs:
  - QLIK-PS-002
related_docs:
  - docs/INDEX.md
  - PROJECT_STATUS.md
  - REQUIREMENTS.md
  - FIXES_APPLIED.md
---

# Project Context

## Purpose

- Liefert einen kompakten Einstieg in `qlik_atlas` fuer neue Agent-Sessions und menschliche Reviewer.
- Erklaert, wie bestehende Root-Dokumente zusammen mit `docs/` genutzt werden.

## Current State

- `qlik_atlas` ist ein Full-Stack-Projekt mit `backend`, `frontend`, `db` und Docker-Setup.
- Produktanforderungen/Sicherheits-/Testing-Regeln werden ueber zentrale `general` Specs und projektspezifische Specs in `.product-specs/` gesteuert.
- Projektdokumentation startet ueber `docs/INDEX.md`, verweist aber aktuell noch auf bestehende Root-Dokumente als Hauptquellen.
- Laufende Architekturmigration: User-facing Runtime-Reads sind DB-only (RLS-scoped); Fetch-Jobs laufen standardmaessig DB-first ohne lokale Fetch-Artefakte.

## Key Facts

- Projektstruktur (sichtbar im Repo): `backend/`, `frontend/`, `db/`, `.product-specs/`, `docs/`
- DB Source of Truth (laufend umgesetzt):
  - Dashboard-/Lineage-Reads: PostgreSQL / RLS
  - Zielbild fuer weitere App-/Lineage-nahe Runtime-Reads: DB-only
  - Lokale Artifacts (`backend/output/...`) sind nicht mehr als Runtime-Source-of-Truth vorgesehen
- Relevante Root-Dokumente:
  - `REQUIREMENTS.md` (Roadmap / Implementierungsanforderungen)
  - `PROJECT_STATUS.md` (aktueller Umsetzungsstatus)
  - `FIXES_APPLIED.md` (historische Fixes / Ursachen)
- Agent-Governance:
  - Repo-`AGENTS.md` enthaelt nur den neutralen Verweis auf die private Bridge unter `<KI_ROOT>\projects\qlik_atlas\AGENTS.md`
  - Zentrale Specs / Masterprompts liegen unter `<KI_ROOT>`

## How To Use Documentation (Agent + Mensch)

- Fuer neue Sessions zuerst `docs/INDEX.md` lesen.
- Danach die dort markierten Root-Dokumente lesen.
- Specs und Masterprompts bleiben verbindlich; Doku liefert Kontext/Status und darf Sicherheitsregeln nicht abschwaechen.
- Bei Widerspruch gilt standardmaessig: Specs > Docs.

## Open Questions / Risks

- Root-Dokumente sind noch nicht vollstaendig auf das neue Doku-Schema (Metadaten + Doc Types) migriert.
- Release Notes liegen aktuell verteilt (Commit-Nachrichten/Dateien); `docs/RELEASE_NOTES/` ist vorbereitet, aber noch nicht als primaere Quelle etabliert.

## References

- `docs/INDEX.md`
- `../REQUIREMENTS.md`
- `../PROJECT_STATUS.md`
- `../FIXES_APPLIED.md`
- `../.product-specs/spec-index.md`
