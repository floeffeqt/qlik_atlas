---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - docs-cleanup
  - database
  - credentials
  - migration
updated: 2026-02-25
owners: []
source_of_truth: no
related_specs:
  - PS-003
  - PS-004
  - PS-005
  - QLIK-PS-002
related_docs:
  - REQUIREMENTS.md
  - PROJECT_STATUS.md
  - backend/alembic/versions/0008_drop_legacy_qlik_credentials_table.py
---

# Remove Legacy `qlik_credentials` Table References and Cleanup

## Summary

- Veraltete Doku-Referenzen auf eine separate `QlikCredentials`-Tabelle wurden auf das aktuelle Modell aktualisiert.
- Qlik-Credentials werden im aktuellen Stand in `customers` gespeichert (AES-256-GCM verschluesselt auf Anwendungsebene).
- Eine Cleanup-Migration entfernt die ungenutzte Legacy-Tabelle `qlik_credentials` aus bestehenden Datenbanken.

## Notes

- Das aktuelle produktive Modell bleibt unveraendert: `customers.tenant_url` / `customers.api_key` (verschluesselt).
- Die neue Migration ist defensiv (`DROP TABLE IF EXISTS`) fuer bestehende Umgebungen.
