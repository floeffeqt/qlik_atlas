---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - auth
  - security
  - jwt
  - cookies
  - frontend
  - backend
updated: 2026-03-12
owners: []
source_of_truth: no
related_specs:
  - QLIK-PS-002
  - QLIK-PS-006
  - QLIK-PS-007
  - QLIK-PS-009
related_docs:
  - README.md
  - PROJECT_STATUS.md
  - REQUIREMENTS.md
---

# Release Note: Auth Cookie Session Hardening

## Datum

- 2026-03-12

## Summary

- Der JWT Access Token wird im Atlas-Frontend nicht mehr in `localStorage` gehalten.
- Login setzt jetzt ein backendseitiges `HttpOnly`-Cookie fuer die Session.
- Frontend-Requests nutzen Cookie-basierte Auth statt Bearer-Header aus Browser-JavaScript.

## Backend

- `POST /api/auth/login` setzt ein `HttpOnly`-Cookie und liefert User-Metadaten statt des rohen JWT.
- Neuer Endpoint `POST /api/auth/logout` loescht das Auth-Cookie.
- Auth-Dependencies akzeptieren jetzt Cookie- oder Bearer-basierte Token-Aufloesung, damit bestehende API-Tests/Service-Aufrufe kompatibel bleiben.

## Frontend

- Zentrale Auth-Logik in `frontend/assets/atlas-shared.js` auf Cookie-Transport umgestellt.
- Nur nicht-sensitive User-Metadaten werden noch fuer UI-Hinweise lokal gecacht.
- Direkte Bearer-Header-Nutzung in `lineage.html` und `theme-builder.html` entfernt.

## Tests

- Backend-Auth-Tests auf Cookie-Login, `/api/auth/me` mit Cookie und Logout-Clearing erweitert.
- Zusatztet in `test_auth_utils.py` fuer Cookie-Fallback in der Token-Aufloesung.
- Lokaler Python-Compile-Check erfolgreich; Host-`pytest` war in dieser Session nicht installiert.

## Notes

- Keine DB-Schema-Aenderung.
- `docs/DB_MODEL.md` bleibt unveraendert, weil nur Auth-Transport und Session-Handling angepasst wurden.
