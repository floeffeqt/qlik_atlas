---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - fetch-job
  - backend
  - bugfix
updated: 2026-03-02
owners: []
source_of_truth: no
related_specs:
  - QLIK-PS-007
related_docs:
  - docs/DB_MODEL.md
  - docs/RELEASE_NOTES/README.md
---

# Release Note: Fetch Job Upsert Column Mapping Fix

## Datum

- 2026-03-02

## Problem

- Fetch-Jobs konnten mit einem DB-Fehler fehlschlagen:
  - `column "name_value" of relation "qlik_apps" does not exist`
- Ursache: Bei Core-Upserts (`pg_insert`) wurden teils ORM-Attributnamen statt physischer DB-Spaltennamen uebergeben.

## Umsetzung

- In `backend/main.py` wurde eine zentrale Mapping-Hilfe eingefuehrt:
  - `_to_db_column_value_map(model, values)`
- Diese Mapping-Hilfe wird vor Upserts auf die Payload-Spalten angewendet fuer:
  - `QlikApp`
  - `QlikSpace`
  - `QlikDataConnection`
  - `QlikReload`
  - `QlikAudit`
  - `QlikLicenseConsumption`
  - `QlikAppUsage`

## Wirkung

- Upserts fuer Fetch-Module schreiben jetzt stabil in die korrekten DB-Spalten.
- Fehler wie `name_value does not exist` werden dadurch vermieden.
- Kein DB-Schema-Change erforderlich.

## Verifikation

- Fetch-Job erneut starten.
- Erwartung:
  - Job endet mit `completed` (sofern keine anderen API-/Credential-Probleme vorliegen).
  - Tabellen werden befuellt (`qlik_apps`, optional `qlik_reloads`, `qlik_audits`, `qlik_license_consumption` je nach Steps).

