---
doc_type: template
scope: project
project_key: qlik_atlas
status: active
tags:
  - template
  - bugfix
  - fixes-applied
updated: 2026-03-02
owners: []
source_of_truth: yes
related_specs:
  - QLIK-PS-007
  - QLIK-PS-002
related_docs:
  - FIXES_APPLIED.md
---

# Bugfix Entry Template

## Purpose

- Zentrales, verbindliches Template fuer neue Bugfix-Eintraege in `FIXES_APPLIED.md`.
- Stellt sicher, dass Severity, Ursache, Fix und Testnachweis konsistent dokumentiert werden.

## When To Add An Entry

- Immer wenn im Rahmen einer Aufgabe ein **confirmed bug** behoben wurde.
- Bei mehreren behobenen Bugs: pro Bug ein eigener Eintrag.

## Mandatory Fill Logic

- `Date`: Datum der Umsetzung (`YYYY-MM-DD`).
- `Title`: kurze, eindeutige Bugbeschreibung.
- `Severity`: `critical|high|medium|low` gemaess `QLIK-PS-007`.
- `Area`: betroffener Bereich (z. B. `backend/api`, `frontend/lineage`, `migration/alembic`).
- `Source`: wie entdeckt (`proactive bug-hunt`, `feature regression`, `user-reported`, ...).
- `Symptoms`: beobachtbares Fehlverhalten.
- `Root Cause`: technische Ursache (konkret, nicht nur "Bug in code").
- `Fix`: was geaendert wurde.
- `Changed Files`: relevante Datei-Pfade.
- `Verification`: welcher Test/Check den Fix bestaetigt.
- `Residual Risk`: was ggf. offen bleibt, sonst `none`.

## Entry Format (Copy/Paste)

```md
## [BUGFIX] <YYYY-MM-DD> <Short Title>

- Severity: <critical|high|medium|low>
- Area: <area/module>
- Source: <proactive bug-hunt|feature regression|user-reported|other>
- Symptoms: <what broke / visible impact>
- Root Cause: <technical cause>
- Fix: <what was changed>
- Changed Files: <path1>, <path2>, ...
- Verification: <tests/checks and outcome>
- Residual Risk: <none or explicit residual risk>
```

## Example

```md
## [BUGFIX] 2026-03-02 Alembic version length overflow

- Severity: high
- Area: backend/migrations
- Source: proactive bug-hunt
- Symptoms: backend startup crash during `alembic upgrade head`
- Root Cause: `alembic_version.version_num` length too short for long revision id
- Fix: shortened revision id and added migration to expand `version_num` to `VARCHAR(255)`
- Changed Files: backend/alembic/versions/0013_expand_qlik_data_connections_columns_from_jsonb.py, backend/alembic/versions/0014_expand_alembic_version_num_length.py
- Verification: docker compose restart + backend logs + health endpoint 200 OK
- Residual Risk: none
```
