---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - auth
  - security
  - refresh-token
  - frontend
  - backend
  - database
updated: 2026-03-12
owners: []
source_of_truth: no
related_specs:
  - QLIK-PS-002
  - QLIK-PS-006
  - QLIK-PS-007
  - QLIK-PS-008
  - QLIK-PS-009
related_docs:
  - README.md
  - PROJECT_STATUS.md
  - REQUIREMENTS.md
  - docs/DB_MODEL.md
---

# Release Note: Refresh Token Rotation

## Datum

- 2026-03-12

## Summary

- Browser-Sessions in Atlas haben jetzt neben dem Access-Cookie einen persistierten Refresh-Token-Lifecycle.
- `401`-Antworten loesen im Frontend genau einen Refresh-Versuch aus; bei Erfolg wird der urspruengliche Request wiederholt.
- Refresh-Tokens werden rotiert und serverseitig in der Datenbank gespeichert.

## Backend

- Neue Tabelle `refresh_tokens` fuer persistierte Refresh-Sessions.
- Neuer Endpoint `POST /api/auth/refresh`.
- `POST /api/auth/logout` widerruft den aktuellen Refresh-Token und loescht Access-/Refresh-Cookies.
- Login erstellt jetzt sowohl Access- als auch Refresh-Cookie.

## Frontend

- `frontend/assets/atlas-shared.js` fuehrt bei `401` einen stillen Refresh-Versuch aus.
- Nach erfolgreichem Refresh wird der urspruengliche API-Request einmalig wiederholt.
- Wenn Refresh fehlschlaegt, wird die lokale Session bereinigt und auf `login.html` umgeleitet.

## Tests

- Backend-Tests fuer Login-Cookies, Refresh-Rotation und Logout-Revoke erweitert.
- Lokaler Python-Compile-Check erfolgreich.
- Runtime-Smokes gegen `localhost:8000` und `localhost:4001` pruefen Login -> me -> refresh/logout -> 401 nach Session-Ende.
