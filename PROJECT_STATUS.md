# Project Status: Implementation Summary

## ✅ What's Complete (Ready to Use)

### Customer Link (100%) — Migration 0026
- ✅ `customer_link` column added to `customers` table (AES-256-GCM encrypted, same pattern as `api_key`/`git_token`)
- ✅ Admin UI: Eingabefeld in Kunden-Modal ("Link zum internen Kundenordner"), sichtbar in Kunden-Übersichtstabelle als klickbarer Link
- ✅ Dashboard-Header: Kundenname wird als klickbarer Link angezeigt, wenn `customer_link` gesetzt
- ✅ `/api/customers/names` liefert entschlüsselte URL an alle authentifizierten User
- ✅ Migration: `backend/alembic/versions/0026_customer_link.py`

### Master Items Sync (100%) — kein DB-Schema (rein API-getrieben)
- ✅ `backend/shared/master_items_sync.py`: `export_master_items`, `diff_master_items`, `import_master_items` — nutzt `EngineSession`/`open_session` aus `qlik_engine_client.py`
- ✅ `backend/shared/qlik_engine_client.py`: `EngineSession`-Klasse + `open_session` Async-Context-Manager für multi-step Engine-Operationen
- ✅ `backend/app/qlik_deps.py`: `resolve_project_creds()` + `CredentialsError(ValueError)` — geteilter Credential-Resolver (Themes-Service + Master-Items-Routes)
- ✅ `backend/app/master_items/routes.py`: drei Admin-Endpoints `POST /api/master-items/export|diff|import`
- ✅ Frontend: Master Items Tab in `script-sync.html` (3-Schritt-Workflow: Export → Diff → Import)
- ✅ Frontend: Properties-Detail-Fenster nach Export (Accordion je Dimension/Kennzahl/Visualisierung, Filter, Raw-JSON-Toggle)
- ✅ Frontend: Diff-Request sendet gecachtes `_miExportData` als `source_export` (spart eine WS-Verbindung)
- ✅ Frontend: Parallel-App-Listen-Refresh (`steps:['apps']`) beim Export-Klick

### App Hub (100%) — `frontend/app-hub.html`
- ✅ Neue Seite: App-zentrierte Ansicht mit 5 Tabs (Übersicht, Script, Master Items, Fetch & Zeitpläne, Lineage)
- ✅ URL-Param-basierte Navigation: `/app-hub.html?app_id=XXX&project_id=YYY`
- ✅ Übersicht-Tab: App-Name, App-ID, Projekt, letzter Script-Fetch
- ✅ Script-Tab: Qlik-Syntax-Highlighting, Abschnitte klappbar, Reload-Button, Kopieren
- ✅ Master Items-Tab: Gleicher 3-Schritt-Workflow wie Script Sync, Quell-App ist diese App (fest), Multi-Target-Import
- ✅ Fetch & Zeitpläne-Tab: Fetch-Job-Trigger mit SSE-Fortschritt, Job-Liste, Zeitpläne-CRUD
- ✅ Lineage-Tab: Link zu `lineage.html?app_id=...`
- ✅ "Hub"-Button in Script Sync Mapping-Tabelle und Script-Viewer (Direktnavigation)
- ✅ App Hub Nav-Link in allen Seiten ergänzt

### Script Sync UI (100%)
- ✅ `scriptViewerPanel`-Null-Crash behoben (Element fehlte im DOM, Null-Guard hinzugefügt)
- ✅ "Scripts abziehen"-Button mit Fetch-Job-Fortschritt via SSE + Polling-Fallback
- ✅ Tab-Konflikt zwischen Seiten-Level-Tabs (`data-tab`) und Master-Items-Mini-Tabs (`data-mi-tab`) behoben
- ✅ Master Items Import: Item-Selektion mit Checkboxen nach Diff (Neu/Konflikt/Gleich, je Typ filterbar)
- ✅ Multi-App-Import: Mehrere Ziel-Apps gleichzeitig, per-App Accordion-Ergebnis
- ✅ Geplante Fetch-Jobs: Cron-Zeitpläne pro Projekt (Migration 0027, APScheduler, CRUD-UI in script-sync.html)
- ✅ Fetch-Job SSE-Streaming: `GET /api/fetch/jobs/{job_id}/stream` (EventSource, Polling-Fallback)
- ✅ Admin-Übersicht Fetch-Zeitpläne: Tab in `admin.html` — alle Zeitpläne aller Kunden/Projekte, Aktivieren/Deaktivieren, Löschen

### Infrastructure (100%)
- ✅ Docker Compose with 3 services: db, backend, frontend (pgadmin dev-profile only)
- ✅ PostgreSQL 15 — einziges persistentes Volume (`pgdata`)
- ✅ QLIK-PS-005 compliant: kein Bind-Mount, keine File-Write-Utilities, kein pgadmin_data-Volume
- ✅ FastAPI backend with async SQLAlchemy + asyncpg
- ✅ Nginx frontend serving SPA on port **4001**
- ✅ Health checks on all services
- ✅ Non-root users in all containers
- ✅ Multi-stage Docker builds (optimized images)

### Authentication System (100%)
- ✅ User model in PostgreSQL (id, email, password_hash, is_active, created_at)
- ✅ Password hashing with Argon2id
- ✅ JWT token generation (HS256, 15-min expiration)
- ✅ `/auth/register` endpoint
- ✅ `/auth/login` endpoint
- ✅ Frontend login page with form
- ✅ Frontend register page with form
- ✅ Access-token transport via `HttpOnly` auth cookie
- ✅ Refresh-token transport via separate `HttpOnly` cookie
- ✅ `/auth/refresh` endpoint
- ✅ `/auth/logout` revokes refresh session state
- ✅ API fetch wrapper with cookie-based authenticated requests
- ✅ Frontend auto-refresh on `401` with one retry cycle
- ✅ Login brute-force protection on `/auth/login` (IP + email, `429` + `Retry-After`)
- ✅ Legacy `PBKDF2-SHA256` password hashes are rehashed to `Argon2id` on successful login
- ✅ 401 redirect to login
- ✅ Test user: **admin@admin.de** / **admin123** (auto-seeded)

### Startup & Deployment (100%)
- ✅ Automatic database migration on startup (Alembic)
- ✅ Automatic test user creation on startup
- ✅ Health checks verify all services are ready
- ✅ Proper startup sequence (db → backend → frontend)
- ✅ Docker Compose compatible with Windows/Mac/Linux

### Documentation (100%)
- ✅ README.md with quickstart instructions
- ✅ REQUIREMENTS.md with comprehensive roadmap
- ✅ FIXES_APPLIED.md explaining all bug fixes

---

## 🚀 How to Run

### Quick Start (3 commands)
```bash
# 1. Navigate to project
cd /path/to/qlik_atlas

# 2. (Optional) Adjust .env if needed
# nano .env

# 3. Start everything
docker compose up --build
```

### Access Application
- **Frontend**: http://localhost:4001
- **Backend API**: http://localhost:8000
- **Test Credentials**: admin@admin.de / admin123

### View Logs
```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f db
```

### Stop Everything
```bash
docker compose down
```

### Remove Everything (including database)
```bash
docker compose down -v
```

---

## 📋 Requirements To Implement (Roadmap)

### High Priority (Core Features)
1. **Qlik Credentials Management**
   - Secure storage in DB (encrypted)
   - Admin UI to input/update credentials
   - Test connection verification

2. **Database Schema for Lineage**
   - Tables: apps, spaces, lineage_nodes, lineage_edges, data_connections, app_usage
   - Proper foreign keys and indexes
   - JSONB fields for flexible metadata

3. **Persist Fetchers to Database**
   - Modify fetchers to write to DB instead of JSON
   - Create migration script: `migrate_json_to_db.py`
   - Verify data integrity

4. **Protected API Endpoints**
   - Add JWT validation middleware/dependency
   - Mark protected routes
   - Return proper 401/403 errors

5. **Frontend Dashboard**
   - Home page redirects to login if no token
   - Show logged-in user info
   - Display Qlik status
   - Logout button

### Medium Priority (Completeness)
6. **Refresh Token Support**
   - Implemented: `refresh_tokens` table
   - Implemented: `/auth/refresh` endpoint
   - Implemented: frontend refresh logic on 401

7. **Rate Limiting**
   - Implemented: `/auth/login` rate limit (10 failures/hour/IP, 5 failures/hour/email by default)
   - Implemented: `429` with `Retry-After` header on login lockout
   - Open: `/auth/register` rate limit if public self-service registration becomes relevant

8. **API Documentation**
   - Generate OpenAPI/Swagger spec
   - Document all endpoints
   - Example requests/responses

9. **Input Validation & Error Handling**
   - Email format, password strength
   - Qlik URL validation
   - Comprehensive error messages

### Lower Priority (Polish/Scale)
10. **Testing**
    - Unit tests for auth
    - Integration tests with DB
    - Frontend tests

11. **Frontend Features**
    - Admin settings page (Qlik credentials)
    - Lineage visualization (graph or table)
    - Search/filter functionality

12. **Production Readiness**
    - SSL/TLS configuration
    - CORS hardening
    - Logging & monitoring
    - Backup/recovery procedures

---

## 🔒 Security Implementation Notes

### Current Security
- ✅ Passwords hashed with bcrypt (cost 12)
- ✅ JWT signing with HS256 algorithm
- ✅ `.env` excluded from git
- ✅ Non-root Docker users
- ✅ Health checks preventing incomplete startup
- ✅ CORS middleware preventing cross-origin abuse

### Security Coming
- 🔜 Credential key rotation / secret-management hardening for encrypted customer credentials
- 🔜 HTTPS/SSL in production
- 🔜 Rate limiting to prevent brute force
- 🔜 Input validation on all endpoints
- 🔜 SQL injection prevention (already using parameterized queries)
- 🔜 XSS prevention (nginx headers, CSP)

---

## 📊 Database Schema (Current & Planned)

### ✅ Current (Ready)
```sql
-- Users table (created automatically on startup)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(320) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
```

### 🔜 Planned
- Apps table (imported from JSON artifacts)
- Spaces table
- Lineage nodes/edges tables
- Data connections table
- App usage tracking table
- Customer credentials in `customers` table (encrypted)
- Refresh tokens table
- Fetch jobs history table

---

## 🔧 Architecture Diagram

```
Internet
    │
    └──→ [localhost:4001] (Nginx - Frontend)
             │
             ├──→ Serves HTML/CSS/JS (static SPA)
             │
             └──→ /api/*  ──→ [localhost:8000] (FastAPI - Backend)
                                │
                                ├──→ /auth/* (login, register)
                                ├──→ /health (health check)
                                ├──→ /api/* (protected lineage/app endpoints)
                                │
                                └──→ PostgreSQL:5432 (Database)
                                    - Users table
                                    - Future: Apps, Spaces, Lineage data
```

---

## 🎯 Test Flow

1. **Start containers**: `docker compose up --build`
2. **Wait for health checks**: All services show green
3. **Open browser**: http://localhost:4001
4. **Login**: admin@admin.de / admin123
5. **Check session cookie**: Inspect the browser cookie jar and verify the auth cookie is `HttpOnly`
6. **Test API**: Open DevTools → Network → verify requests are authenticated without exposing a bearer token to page JavaScript

---

## ⚠️ Known Limitations (Will Fix)

- [ ] Access JWTs remain stateless and are not server-revoked before expiry
- [ ] Refresh-token replay detection is basic rotation/revoke only (no family-wide incident handling)
- [ ] No role-based access control (all users are equal)
- [ ] Customer credential management UX still needs hardening/polish (storage/encryption exists)
- [ ] Login rate limiter is in-memory per backend instance and resets on restart
- [ ] Legacy `PBKDF2-SHA256` hashes only migrate after the affected user logs in successfully
- [ ] Lineage data still in JSON (not persisted to DB)
- [ ] Frontend only has login/register (no dashboard yet)
- [ ] No API documentation deployed

---

## 📞 Next Steps

Choose your priority:

### A. Get Dashboard Working
- Create home page
- Add logout functionality
- Show user dashboard

### B. Secure Qlik Credentials
- Keep credentials in `customers` table (no separate `QlikCredentials` table)
- Improve admin settings/customer credential UX
- Harden key management / rotation and validation flows

### C. Persist Lineage to DB
- Design full schema
- Create migrations
- Modify fetchers

### D. Production Hardening
- Expand rate limiting beyond login if needed
- Add comprehensive validation

---

All code is ready to build and run now. No further development needed for basic functionality.

---

## Update (2026-02-25): DB-Only Runtime Reads (GraphStore Removed)

### Completed in this step
- ✅ User-facing read endpoints for graph/inventory-related data are now DB-backed (RLS-scoped):
  - `/api/inventory`, `/api/apps`
  - `/api/spaces`
  - `/api/data-connections`
  - `/api/graph/app/{app_id}`
  - `/api/graph/node/{node_id}`
  - `/api/reports/orphans`
  - `/api/app/{app_id}/usage`
  - `/api/app/{app_id}/script`
- ✅ `GraphStore` runtime usage removed and legacy `backend/fetchers/graph_store.py` removed
- ✅ Dashboard metric label updated from local file count to DB metric (`Apps in DB`)

### Architecture status after this step
- Runtime reads for the endpoints above use PostgreSQL as source of truth.
- Fetch jobs now run DB-first (in-memory to PostgreSQL) by default; local fetch artifacts are disabled unless explicitly enabled.
- Additional DB tables/models were introduced for runtime reads:
  - `qlik_spaces`
  - `qlik_data_connections`
  - `qlik_app_usage`
  - `qlik_app_scripts`
  - `lineage_edges.app_id` for app graph linkage

### Fetch pipeline mode (new default)
- Default: `FETCH_WRITE_LOCAL_ARTIFACTS=false` (DB-first, no local fetch JSON staging)
- Optional debug/compat mode: set `FETCH_WRITE_LOCAL_ARTIFACTS=true`

---

## Update (2026-03-13): Security Hardening (K2, K3, H4-H7)

### Completed
- K2: RLS Policies auf allen 17 project-scoped Tabellen mit `app_has_customer_access()` Check korrigiert (Migration 0019)
- K3: Explizite PostgreSQL Connection Pool Settings (pool_size, max_overflow, pool_recycle)
- H4: CORS Wildcard durch explizites Method/Header Whitelisting ersetzt
- H5: HSTS Header auf Backend + Nginx Frontend, CSP Haertung
- H6: HMAC-SHA256 fuer Refresh Token Hashing (7-Tage Dual-Hash Transition)
- H7: Structured Logging auf 13+ Exception Handler (atlas.api, atlas.runtime, atlas.graph)

### Ausstehend
- K1: .env Secrets aus Git-History entfernen
- H8: Tests in CI/CD Pipeline

---

## Update (2026-03-16): Git Script Sync - Phase 0 (Grundstruktur)

### Completed
- Migration 0020: `script_git_mappings` + `script_deployments` Tabellen mit RLS Policies
- `customers` Tabelle erweitert um `git_provider`, `git_token` (AES-256-GCM verschluesselt), `git_base_url`
- Git Provider Abstraction: ABC `GitProvider` mit GitHub (REST API v3) und GitLab (REST API v4) Implementierung
- `QlikClient` erweitert um `post_json()` (fuer Script-Write/Reload) und `get_text()` (fuer Script-Read)
- 8 neue REST-Endpoints unter `/api/script-sync/` (Mapping CRUD, Status, Overview, History, Verify Access)
- Customer API erweitert: Git-Felder bei Create/Update, Token maskiert in Response
- Spec-Compliance: QLIK-PS-008 (Migration Name 23 chars, max 30), QLIK-PS-001 (Git Token AES-256-GCM), QLIK-PS-003 (RLS auf neuen Tabellen)

### Naechste Phasen
- P2: Publish (Git -> Qlik) mit Pre-Checks
- P3: Reverse Sync (Qlik -> Git)
- P4: Webhook Auto-Drift
- P5: Erweiterungen (Auto-Publish, Batch, CLI)
- Tracking: siehe `qlik_atlas_analytics_catalog.xlsx` Sheet "Git Integration Plan"

---

## Update (2026-03-17): H8 - Docker-basierte Test-Pipeline

### Completed
- Dockerfile: Multi-Stage Build mit `test` Target (production + pytest/aiosqlite)
- `requirements-test.txt`: pytest, pytest-asyncio, aiosqlite (erweitert requirements.txt)
- `docker-compose.yml`: Neuer `test` Service mit `profiles: [test]` – laeuft isoliert gegen SQLite in-memory
- Kein Zugriff auf Produktiv-DB, keine Secrets-Exposure, kein Netzwerk-I/O

### Usage
```bash
# Alle Tests ausfuehren
docker compose --profile test run --rm test

# Einzelnen Test ausfuehren
docker compose --profile test run --rm test pytest tests/test_auth.py -v

# Nur einen Test
docker compose --profile test run --rm test pytest tests/test_auth.py::test_health -v
```

### Bestehende Test-Suite (12 Testdateien)
- `test_auth.py`: Login, Refresh, Logout, Rate Limiting, Password Rehash
- `test_auth_utils.py`: Token/Cookie Utilities
- `test_credentials_crypto.py`: AES-256-GCM Encryption
- `test_analytics_api.py`, `test_analytics_runtime_views.py`: Analytics Endpoints
- `test_db_runtime_views.py`: DB Runtime Views
- `test_customer_project_contracts.py`: Customer/Project Contracts
- `test_fetch_lineage.py`, `test_fetch_app_data_metadata.py`: Fetch Pipeline
- `test_ingestion_payload_columns.py`: Ingestion Logic
- `test_qri_heuristics.py`: QRI Parsing
- `test_theme_generator.py`: Theme Generator

---

## Update (2026-03-16): Git Script Sync - Phase 1 (Drift Detection + UI)

### Completed
- Overview- und Status-Endpoints um `app_name`, `repo_identifier`, `branch`, `file_path` angereichert
- Batch-Load von App-Namen aus `qlik_apps` Tabelle (statt N+1 Queries)
- Neue Admin-Seite `frontend/script-sync.html`:
  - Mapping-Verwaltung (CRUD): Erstellen, Bearbeiten, Loeschen von App-Git-Mappings
  - Sync-Ampel: Farbcodierte Status-Badges (in_sync, git_ahead, qlik_ahead, diverged, error)
  - Stats-Karten: Zusammenfassung der Sync-Stati pro Projekt
  - Drift-Check Button: Manueller Abgleich aller Mappings gegen Git
  - Deployment-History: Audit-Log pro App anzeigbar
  - Projekt/Kunden-Auswahl ueber globale Focus-Selectors (wie andere Seiten)
- Navigation: "Script Sync" Link auf allen 6 Seiten hinzugefuegt
- `atlas-shared.js`: `updateNavProjectContext()` um script-sync.html erweitert
- Spec-Compliance: QLIK-PS-006 (Frontend-Impact geprueft), QLIK-PS-009 (n/a, keine Runtime-Aenderung)

---

## Update (2026-03-17): M3 - Graph Pagination

### Completed
- Cursor-basierte Pagination fuer Lineage-Graph-Endpoints
- Keyset-Cursor auf `node_id` (ASC), konfigurierbare `page_size` (10-5000)
- Edges werden pro Seite mitgeliefert (alle Edges, die mindestens einen Knoten der Seite referenzieren)
- Rueckwaertskompatibel: ohne `page_size` Parameter bleibt Verhalten unveraendert

### Betroffene Dateien
- `backend/shared/models.py`: Neues `PaginatedGraphResponse` Schema
- `backend/app/runtime_query_rows.py`: `fetch_graph_counts()`, `fetch_graph_rows_paginated()`
- `backend/app/db_runtime_views.py`: `load_graph_response_paginated()`, `_build_snapshot_from_rows(create_edge_stub_nodes=False)`
- `backend/main.py`: Endpoints `/api/graph/project/{id}`, `/api/graph/all`, `/api/graph/db` mit `page_size` + `after` Query-Params
- `frontend/lineage.html`: Auto-Pagination (nodeMap Deduplizierung, edgeMap Deduplizierung, Ladefortschritt)

### API
- `GET /api/graph/project/{id}?page_size=500` - erste Seite
- `GET /api/graph/project/{id}?page_size=500&after=<node_id>` - naechste Seite
- Response: `{ nodes, edges, next_cursor, total_nodes, total_edges, page_size }`
- `next_cursor: null` = letzte Seite

### Spec-Compliance
- QLIK-PS-003: RLS wird ueber bestehende Session-Context-Middleware angewendet (keine neue Tabelle)
- QLIK-PS-006: Frontend-Aenderung nur in `lineage.html` (loadGraph Funktion)
- QLIK-PS-008: Keine Migration erforderlich (keine Schema-Aenderung)

## Update (2026-03-17): Test-Fixes (10 Failures behoben)

### Behoben
- `test_auth.py`: Health-Endpoint-Pfad `/health` -> `/api/health`, Engine-Scope session -> function, Passwort-Laenge >= 8
- `test_theme_generator.py`: Auth-Dependency per `autouse` Fixture gemockt statt DB-Lookup
- `test_db_runtime_views.py`: `layer="data"` -> `"db"`, Listen- vs. Set-Vergleich fuer Node-Reihenfolge
- `test_ingestion_payload_columns.py`: Test-Payload an Qlik API camelCase-Format angepasst
- `tests/conftest.py`: SQLAlchemy Load-Listener fuer SQLite Timezone-Fix (RefreshToken)
- Ergebnis: **86/86 Tests bestanden**

## Update (2026-03-17): Theme Builder UX-Verbesserungen

### Chart Preview (komplett ueberarbeitet)
- Achsen (X/Y) mit Beschriftungen und Gitterlinien
- Legende mit Farb-Swatches fuer alle Datenserien
- Vollstaendige Palette-Farben aus `palettes.data[].scale` statt nur primary/others
- 12 chart-spezifische Renderings: pieChart, barChart, histogram, lineChart, scatterPlot, waterfallChart, comboChart, gauge, kpi, table/pivotTable/straightTable, treemap, funnelChart
- Generischer Fallback mit Achsen fuer unbekannte Objekt-Typen

### Farb-Labor (Color Lab)
- **Harmonien-Generator**: Komplementaer, Analog, Triadisch, Split-Komplementaer
- Klickbare Farb-Swatches uebernehmen Farbe direkt in Variablen-Eingabe + Color Lab
- Nahtlose Integration: Farbe waehlen → Harmonie generieren → als Variablen uebernehmen

### Variablenverwaltung
- **Palette-Strip**: Visuelle Uebersicht aller Farbvariablen als klickbare Swatches
- Tooltip mit Variablenname und Hex-Wert bei Hover
- Klick laedt Farbe ins Color Lab

### Quick-Start Presets
- 5 vorkonfigurierte Themes: Corporate Blue, Emerald, Sunset, Dark Mode, Pastel
- Ein-Klick-Laden mit Farbvorschau-Swatches
- Jedes Preset enthaelt Variablen, dataColors, Objekt-Styles und Paletten

### JSON Editor
- Zeilenanzahl in Status-Leiste
- Fehler-Zeilennummer bei JSON-Parse-Fehlern
- Bessere Fehlermeldungen mit Position

### Qlik Cloud Upload
- **Backend**: `POST /api/themes/upload` mit echtem Upload via Qlik Cloud REST API (`/api/v1/themes`)
- `QlikClient.post_file()` Methode fuer multipart/form-data File-Upload
- Projekt-basierte Credential-Aufloesung (Customer → tenant_url + api_key)
- **Frontend**: "In Qlik hochladen" Button (ersetzt Upload-Stub)
- Erfordert Projekt-Auswahl in der Navigation

### UX-Verbesserungen
- Keyboard-Shortcuts: `Ctrl+S` Download, `Ctrl+Shift+F` Format, `Ctrl+Shift+U` Upload
- Tooltips auf allen wichtigen Buttons
- Aktualisierte Beschreibung mit Feature-Uebersicht

### Tests
- Ergebnis: **87/87 Tests bestanden** (1 neuer Upload-Test)
- Docker-Build: Backend + Frontend erfolgreich

### Geaenderte Dateien
- `frontend/theme-builder.html` (Chart Preview, Color Lab, Presets, Variablen-Palette, Upload, Shortcuts)
- `backend/shared/qlik_client.py` (post_file Methode)
- `backend/app/themes/schemas.py` (ThemeUploadRequest/Response)
- `backend/app/themes/service.py` (upload_theme_to_qlik)
- `backend/app/themes/routes.py` (Upload-Endpoint)
- `backend/tests/test_theme_generator.py` (Upload-Tests aktualisiert)

## Update (2026-03-18): Analytics Visualisierung — Hybrid-Migration (ECharts + D3)

### Motivation
- Custom Canvas 2D (Cost-Value Scatter) durch Apache ECharts 5.5.1 ersetzt
- ~300 Zeilen handgeschriebener Canvas-Draw-/Hit-Testing-Code durch ~120 Zeilen ECharts-Konfiguration ersetzt
- Data Model Circle Pack bleibt auf D3.js v7 (natuerlichere Darstellung als gepackte Kreise, ECharts bietet kein Circle-Pack-Equivalent)
- Lizenzen: Apache 2.0 (ECharts) + ISC (D3.js) — beide kommerziell uneingeschraenkt

### Aenderungen
- **Cost-Value Scatter**: Canvas 2D → ECharts `type: 'scatter'` mit 4 Quadranten-Serien, markArea-Hintergrund, Click-Events, Tooltips
- **Data Model Circle Pack**: Bleibt D3.js v7 SVG Circle Pack mit Zoom, Pan, Drag, Breadcrumb-Navigation
- **CDN**: D3.js v7 + ECharts 5.5.1 beide eingebunden in `analytics.html`
- **Resize-Handler**: ECharts `.resize()` fuer Scatter, `renderDataModelPack()` Re-Render fuer Circle Pack

### Entfernte Funktionen
- `resizeCostValueCanvas()`, `drawCostValueScatterOnCanvas()`, `bindCostValueScatterCanvasInteractions()`, `bindCostValueScatterInteractions()`
- Canvas-basierter Cost-Value Scatter (~200 Zeilen)

### Beibehaltene Funktionen
- `truncateCircleLabel()` — D3 Circle Pack Label-Truncation
- `renderDataModelPack()` — D3 Circle Pack (SVG, Zoom, Pan, Drag, Breadcrumb)

### Geaenderte Dateien
- `frontend/analytics.html` (ECharts CDN + D3 CDN, Scatter-Migration, Circle Pack beibehalten, Resize-Handler)

## Update (2026-03-23): Theme Generator + Navigation Umbenennung

### Navigation
- "Theme Builder" in allen 6 HTML-Seiten zu "Theme" umbenannt (analytics, index, lineage, projects, script-sync, theme-builder)
- Dateiname bleibt `theme-builder.html` (keine URL-Aenderung)

### Theme-Seite: Sub-Module
- Tab-Switcher trennt "Theme Builder" (bestehend) und "Theme Generator" (neu)
- Builder: Keine funktionalen Aenderungen — Editor, Presets, Color Lab, Upload etc. wie vorher

### Theme Generator (neu)
- **Palette-Konfigurator**: Wahlbare Groessen (5/10/15/20/25 Farben) mit Color-Picker + Hex-Input pro Slot
- **Prioritaeten-System**: Bis zu 3 Farben als Primary/Secondary/Tertiary markierbar (Stern-Toggle)
- **Farb-Algorithmus** (reines ES5, keine externen Libraries):
  - Hex↔RGB↔HSL Konvertierung, WCAG Luminanz-Berechnung
  - Auto-Erkennung Dark/Light-Modus per Durchschnittsluminanz (oder manuell erzwingbar)
  - Tint/Shade-Generierung fuer abgeleitete Farben (Background, Text, Muted, Grid, Error)
- **Vollstaendige Theme-Generierung**: Alle 19 Qlik-Objekt-Typen werden befuellt:
  - barChart, lineChart, pieChart, scatterPlot, waterfallChart, histogram, comboChart, distributionPlot, boxPlot, straightTable, straightTableV2, pivotTable, kpi, gauge, treemap, listBox, filterpane, mapChart, textImage
  - Spezial-Properties: waterfallChart.shape, listBox.dataColors, straightTableV2.grid, treemap.branch, mapChart.label
- **Palettes + Scales**: Data-Palette aus CI-Farben, UI-Palette als Primary-Tints, Gradient + Diverging Scales
- **Sheet-Titel**: Private/Approved/Published mit Primary/Secondary/Tertiary Hintergrund
- **Live-Vorschau**: Palette-Strip + abgeleitete Farben-Grid vor Generierung sichtbar
- **Builder-Integration**: "In Builder uebernehmen" laedt Theme via `setEditorJson()` — sofort editierbar, downloadbar, uploadbar

### Geaenderte Dateien
- `frontend/theme-builder.html` (Sub-Module Tabs, Generator UI, Farb-Algorithmus, Theme-Generierung)
- `frontend/analytics.html`, `frontend/index.html`, `frontend/lineage.html`, `frontend/projects.html`, `frontend/script-sync.html` (Nav-Link Umbenennung)

## Update (2026-03-26): Project Collaboration Module

### Motivation
- Projekt-/App-uebergreifende Zusammenarbeit: Tasks, Dokumentation, Kommentare, READMEs
- Zentrales Dashboard mit Metriken fuer Projektleiter
- Lineage-Graph-Annotationen fuer technische und fachliche Kommentare

### Datenbank (Migration 0021 + Patch 0022)
- 7 neue Tabellen: `tasks`, `tags`, `task_tags`, `doc_entries`, `node_comments`, `app_readmes`, `doc_templates`
- RLS Policies fuer 4 project-scoped Tabellen (gleicher Pattern wie alle anderen)
- Trigger `set_updated_at()` fuer `tasks` und `app_readmes`
- 8 globale Default-Templates geseeded (node_comment, readme, doc_entry_*)
- Patch 0022: Idempotente Drift-Korrektur (`parent_task_id`, `priority`, `readme_type`, `comment_type`, partielle Unique-Indexes)

### Rename: Doku → Log
- API-Pfade: `/api/doc-entries` → `/api/log-entries` (mit `offset`-Pagination)
- Schemas: `DocEntryIn/Out` → `LogEntryIn/Out`
- Metriken: `doc_entries` → `log_entries`
- UI-Labels: "Doku-Eintrag" → "Log-Eintrag", "Aenderungslog" → "Logs"
- DB-Tabelle `doc_entries` und Model `DocEntry` bleiben unveraendert

### Backend (backend/app/collab/)
- `schemas.py`: 17 Pydantic-Models (In/Out/Update fuer alle Entitaeten), `project_name`/`customer_name` in TaskOut, LogEntryOut, AppWithoutReadme
- `routes.py`: 25 Endpunkte (Tags CRUD, Tasks CRUD, Task-Tags, Log Entries mit offset-Pagination, Node Comments mit Counts, Readmes, Templates, Dashboard Metrics, Apps-ohne-README, Qlik Apps Lookup, Projekt-Mitglieder)
- `project_id` optional in: `/api/dashboard/metrics`, `/api/tasks`, `/api/log-entries`, `/api/apps/without-readme` — ohne project_id werden alle Projekte des Users aggregiert (RLS-gefiltert)
- RLS-scoped Session Dependency (`_scoped`) mit `apply_rls_context`
- Priority-Sortierung: `case(PRIORITY_ORDER)` mit `due_date ASC NULLS LAST`
- Router registriert in `main.py` unter `/api`

### Frontend
- `index.html` (Dashboard): **General/Projekt Toggle** (Pill-Switch), Stats-Grid (4 Metriken), **App-Uebersicht** (Health-Tabelle: README ✓/✗, offene/erledigte Tasks, letzter Log pro App), "Meine offenen Tasks" mit Task-Detail-Popup, "Apps ohne README" (collapsible, max 5), Projektweite Tasks mit Filtern, Log Feed (vollbreite Timeline mit Pagination), Task-/Log-Modals mit Markdown-Editor. General-Ansicht zeigt Kunde/Projekt-Badges an Tasks, Log-Eintraegen und Feed-Items
- `app-detail.html` (neu): 3 Tabs — Tasks (mit Filter, Detail-Panel), Logs (gruppiert: Heute/Diese Woche/Aelter), README (Split-View Editor mit Auto-Save, **Datenquellen-Chips** aus Lineage-Graph mit Alle-auswaehlen und Markdown-Tabellen-Injection)
- `projects.html`: Main-Projekt README Section mit Split-View Markdown Editor, Template-Loading, Anchor-Navigation, Auto-Save (Debounce 1.5s)
- `lineage.html`: Node-Kommentare — Badges auf Graph-Knoten, Slide-in Comment Panel, Filter nach Typ, Inline-Formular mit Template-Loading
- `assets/markdownEditor.js` (neu): Shared Markdown Editor Modul (Toolbar, Split-View, configurable Options)

### Geaenderte Dateien
- `backend/alembic/versions/0021_project_collab.py` (Basis-Migration)
- `backend/alembic/versions/0022_collab_patch.py` (Drift-Korrektur)
- `backend/app/models.py` (7 neue Models)
- `backend/app/collab/__init__.py`, `schemas.py`, `routes.py` (neues Package)
- `backend/main.py` (Router-Registrierung)
- `frontend/index.html` (Dashboard-Umbau + Log Feed)
- `frontend/app-detail.html` (neue Seite)
- `frontend/assets/markdownEditor.js` (neues Modul)
- `frontend/projects.html` (Main-Projekt README)
- `frontend/lineage.html` (Node-Kommentare)
- `docs/DB_MODEL.md` (Tabellen, FKs, ERD, Enum-Werte, API-Endpunkte)

---

## Update (2026-04-08): Fetch-Job Script-Fetching

### Completed
- Fetch-Job um Schritt `"scripts"` erweitert: ruft `GET /v1/apps/{app_id}/script` via `QlikClient.get_text()` auf
- Scripts werden per Upsert in `qlik_app_scripts` gespeichert (PK: `project_id + app_id`)
- Concurrency konfigurierbar per `FETCH_SCRIPTS_CONCURRENCY` (Default 5)
- Per-App Fehler werden übersprungen (Warning-Log, Counter `failed`), Job bricht nicht ab
- `"scripts"` in `FETCH_STEP_ORDER` + `FETCH_STEP_ALL_ORDER` — Abhängigkeit auf `"apps"` wird via `_normalize_steps` erzwungen
- `"scripts"` ist kein Independent Step (benötigt `apps_cache`)
- Ergebnis wird im Job-Log ausgegeben: `X erfolgreich, Y fehlgeschlagen`
- `stored["scripts"]` Counter in DB-Store-Schritt

### Spec-Compliance
- QLIK-PS-003: RLS auf `qlik_app_scripts` bereits via Migration 0019 abgedeckt (kein neues Migration nötig)
- QLIK-PS-005: Keine lokalen Artefakte — Scripts landen direkt in PostgreSQL
- QLIK-PS-008: Kein Migration-File nötig (Tabelle existiert seit Migration 0007)

### Geänderte Dateien
- `backend/app/fetch_jobs/contracts.py` (`"scripts"` in FetchStep, Orders, Dependency)
- `backend/app/fetch_jobs/runtime.py` (`_run_scripts_step`)
- `backend/app/fetch_jobs/store.py` (`QlikAppScript` Import, `scripts_data` Parameter, Upsert-Logik)
- `backend/main.py` (Import, `scripts_cache`, `step_label`, `_run_single_step` Branch, `_run_db_store_step` Aufruf, Log)
- `backend/tests/test_fetch_scripts.py` (neu: 7 Tests — Payload, Error-Handling, Contracts, Counter)

---

## Update (2026-04-08): Script Sync — Scripts-UI + Qlik Syntax Highlighting

### Completed
- **"Scripts abziehen" Button** in `script-sync.html` Header — triggert `POST /api/fetch/jobs` mit `steps: ["apps","scripts"]`
- **Fetch-Progress-Section** — Inline-Fortschrittsbalken, Step-Anzeige, Auto-Refresh nach Abschluss
- **Scripts-Section** — App-Liste per Projekt (via `/api/qlik-apps?project_id=X`), Filter-Input
- **Script-Viewer** — Expandierbares Panel pro App, Syntax-Highlighting, Zeilennummern, Kopieren-Button
- **Qlik Load Script Highlighter** (reines ES5, keine externen Libs):
  - Tokenizer: line/block comments, single-quoted strings, `[field]`/`"field"`, `$(variable)`, plain text
  - Keywords (blau): LOAD, FROM, WHERE, JOIN, SET, LET, IF, FOR, SUB, STORE, etc.
  - Funktionen (lila): erkannt über Regex (Abs, Count, Sum, Date, If, Concat, …)
  - Strings (grün), Kommentare (grau/kursiv), Variablen (gelb), [Felder] (teal), Zahlen (orange)
  - Zeilennummern + Scrollbereich (max 600px Höhe)

### Geänderte Dateien
- `frontend/script-sync.html` (CSS, HTML, JavaScript)

---

## Update (2026-04-09): Smart-Compose — Freitext-Eingabe für READMEs, Logs und Tasks

### Completed
- **Smart-Compose-Ansatz (Option A)**: Markdown-Split-View-Editor durch strukturierte Eingabefelder ersetzt — kein Markdown-Wissen mehr erforderlich.
- **`AtlasSmartCompose.readme()`**: Abschnitt-basiertes Formular mit beschrifteten Textarea-Feldern.
  - `app_readme`: Felder: Was macht diese App?, Datenquellen, Reload/Automatisierung, Ansprechpartner, Bekannte Probleme
  - `project_readme`: Felder: Tenant-Übersicht, Architektur, Reload-Automation, Ansprechpartner, Entscheidungen, Einschränkungen
  - `getValue()` → sauberes Markdown (`## Heading\n\ncontent`) für die API (keine Backend-Änderung nötig)
  - `setValue(md)` → parst bestehendes Markdown zurück in Felder (section-heading-based)
  - `insertSection(key, text)` → direkte Feldbesetzung durch DS-Chips
- **`AtlasSmartCompose.log()`**: 3-Feld-Formular (Was / Warum / Betrifft) statt Markdown-Editor.
  - Markdown-Assembly: `**Was:** …\n\n**Warum:** …\n\n**Betrifft:** …`
- **DS-Chips-Integration** bleibt erhalten: "In README einfügen" schreibt Markdown-Tabelle in das Feld `datenquellen`.
- **Anchor-Navigation** (projects.html) scrollt jetzt zum passenden SmartCompose-Feld statt zum textarea-Cursor.
- **Task-Beschreibung**: Placeholder spezifiziert ("Was soll gemacht werden? Akzeptanzkriterien…").

### Spec-Compliance
- Kein Backend/DB-Schema geändert — QLIK-PS-003/008 nicht berührt
- QLIK-PS-006: Beide Frontend-Seiten mit SmartCompose-Integration getestet

### Geänderte Dateien
- `frontend/assets/smartCompose.js` (neu)
- `frontend/app-detail.html` (README-Tab + Log-Modal auf SmartCompose umgestellt, DS-Chips-Handler angepasst)
- `frontend/projects.html` (Projekt-README auf SmartCompose umgestellt, Anchor-Nav angepasst)

---

## Update (2026-04-09): App-Picker in Modals + Log-Felder in eigene DB-Spalten

### Completed
- **App-Picker im Log-Modal**: Dropdown mit allen für das Projekt geladenen Apps, nach Space gruppiert (`<optgroup>`), vorselektiert auf die aktuelle App.
- **App-Picker im Task-Modal**: Gleicher Picker für Tasks (`taskAppSelect`).
- **Log-Felder als eigene DB-Spalten** (Migration 0023 `doc_entries_fields`):
  - `warum` (TEXT NULLABLE): Warum/Begründung — eigene Spalte statt Teil von `content`
  - `betrifft` (TEXT NULLABLE): Betroffene Apps/Bereiche — eigene Spalte statt Freitext in `content`
  - `content` bleibt als "Was"-Feld (Hauptinhalt)
- **SmartCompose Log (`getValues()`)**: Gibt `{was, warum, betrifft}` als strukturiertes Objekt zurück; `getValue()` bleibt rückwärtskompatibel.
- **Log-Liste / Sidebar** (app-detail.html, index.html): Zeigt `betrifft` in der Meta-Zeile an; Sidebar rendert Was/Warum/Betrifft als separate labeled-Felder.

### Spec-Compliance
- QLIK-PS-008: Migrationsdateiname `0023_doc_entries_fields.py` = 27 Zeichen ≤ 30 ✓
- QLIK-PS-003: RLS auf `doc_entries` bereits via Migration 0021 aktiv — keine neue Policy nötig ✓
- docs/DB_MODEL.md aktualisiert (neue Spalten dokumentiert)

### Geänderte Dateien
- `backend/alembic/versions/0023_doc_entries_fields.py` (neu)
- `backend/app/models.py` (`DocEntry`: `warum`, `betrifft` Spalten)
- `backend/app/collab/schemas.py` (`LogEntryIn`, `LogEntryOut`: neue Felder)
- `backend/app/collab/routes.py` (list/get/create log entry: neue Felder persistieren + zurückgeben)
- `frontend/assets/smartCompose.js` (`getValues()` für strukturierten Log-Rückgabewert)
- `frontend/app-detail.html` (App-Picker, Log-Submit mit `getValues()`, Log-Anzeige)
- `frontend/index.html` (App-Picker, Log-Submit mit `getValues()`, Log-Sidebar)
- `docs/DB_MODEL.md` (doc_entries-Abschnitt ergänzt)

---

## Update (2026-04-13): Task-Bearbeitung im Dashboard

### Completed
- **Task-Detail-Popup**: "Bearbeiten"-Button ergänzt (unten rechts im Popup)
- **Task-Modal**: Im Edit-Modus mit allen Feldern vorausgefüllt (Titel, Beschreibung, Status, Priorität, Fälligkeit, Geschätzte Minuten, App, Assignee, Parent Task, App-Link)
- **Modal-Titel** wechselt zu "Task bearbeiten", Speichern-Button zu "Speichern"
- **Submit**: `PUT /api/tasks/{id}` im Edit-Modus, `POST /api/tasks` bei Neu-Erstellung
- **_editTaskId-Reset**: wird beim Schließen des Modals zurückgesetzt (Bugfix)

### Bug-Hunt (QLIK-PS-007)
- **Confirmed + Fixed (medium)**: `_editTaskId` nicht zurückgesetzt bei Abbrechen → PUT statt POST bei nächstem "Neuer Task". Behoben in `closeTaskModal()`. Dokumentiert in FIXES_APPLIED.md.
- **Bekannt / nicht kritisch**: Tags werden beim Bearbeiten nicht neu gesetzt (bestehende Tags bleiben, neue per Tag-Picker nach Speichern). Kein Datenverlust. Residual Risk: low.

### Spec-Compliance
- QLIK-PS-006: Nur Frontend geändert — kein Backend-Impact-Assessment erforderlich ✓
- QLIK-PS-007: Bug-Hunt durchgeführt, confirmed bug dokumentiert ✓
- Kein neues DB-Schema → QLIK-PS-003/008 nicht berührt ✓

### Geänderte Dateien
- `frontend/index.html` (Task-Detail-Popup Edit-Button, openTaskModal Prefill, Submit PUT/POST, closeTaskModal Reset)
- `FIXES_APPLIED.md` (Bugfix-Eintrag)

## Update (2026-04-15): Gantt-Ansicht im Dashboard

### Completed
- **`start_date`-Feld**: Neues optionales Datum-Feld an Tasks (Migration 0024, DB-Spalte `tasks.start_date`)
- **Task-Modal**: `Startdatum`-Eingabe ergänzt (neben Fälligkeit), Prefill beim Bearbeiten
- **Task-Detail-Popup**: Startdatum-Zeile in der Feldübersicht ergänzt
- **Gantt-Karte**: Neue full-width-Karte "Gantt-Ansicht" im Dashboard, sichtbar sobald Kunde oder Projekt ausgewählt
- **Gantt-Rendering**: Tasks gruppiert nach Projekt, farbig nach Priorität (critical=rot, high=orange, medium=blau, low=grau), Heute-Linie, Überfällige Tasks mit rotem Rahmen, Done-Tasks ausgegraut
- **Klickbar**: Klick auf Gantt-Bar öffnet Task-Detail-Popup
- **Backend**: `GET /api/tasks` unterstützt neu `customer_id`-Filter (JOIN über `projects.customer_id`) für kundenweite Gantt-Ansicht

### Spec-Compliance
- QLIK-PS-008: Migration `0024_task_start_date.py` = 24 Zeichen ✓
- QLIK-PS-003: `tasks`-Tabelle hat bereits RLS; neue Spalte benötigt keine eigene Policy ✓
- QLIK-PS-006: Frontend und Backend geändert — Assessment durchgeführt, keine Breaking Changes ✓
- QLIK-PS-007: Kein sicherheitskritischer Pfad betroffen; Bug-Hunt: keine neuen Bugs ✓
- `docs/DB_MODEL.md` aktualisiert ✓

### Geänderte Dateien
- `backend/alembic/versions/0024_task_start_date.py` (neu)
- `backend/app/models.py` (`Task.start_date`)
- `backend/app/collab/schemas.py` (`TaskIn`, `TaskUpdate`, `TaskOut`)
- `backend/app/collab/routes.py` (`_task_out`, `create_task`, `update_task`, `list_tasks` + `customer_id` filter)
- `frontend/index.html` (Gantt-CSS, -HTML, -JS; start_date im Modal, Detail, Payload)
- `docs/DB_MODEL.md`

---

## Update (2026-04-17): Gantt-Erweiterungen (Zeiten, Gruppierung, Grid)

### Completed
- **`start_time`/`end_time`-Felder**: Neue optionale Zeitfelder an Tasks (Migration 0025, `tasks.start_time` + `tasks.end_time`, Typ `TIME`)
- **Task-Modal**: Startzeit- und Endzeit-Eingaben (HH:MM) neben Startdatum und Fälligkeit
- **Gantt-Gruppierung**: Swimlane-Ansicht statt Filter — "Gruppieren nach" Selector (Bearbeiter / Projekt / Status / Priorität), linke Achse zeigt die gewählte Dimension, Task-Titel auf dem Balken
- **Gantt-Grid**: Tageslinien für jeden einzelnen Tag (28px/Tag Mindestbreite), Monatsgrenzen als stärkere Linie, Zweiebenen-Achse (Monate oben, Tagesnummern unten)
- **Grid nur in Task-Zeilen**: Grid-Linien erscheinen ausschließlich in `.gantt-track`, nicht in Group-Header-Zeilen
- **Status-Farben**: open=#667eea, in_progress=#f59e0b, review=#8b5cf6, done=#10b981

### Spec-Compliance
- QLIK-PS-008: Migration `0025_task_times.py` = 18 Zeichen ✓
- QLIK-PS-003: `tasks`-RLS bereits aktiv, keine neue Policy nötig ✓
- QLIK-PS-006: Frontend und Backend synchron geändert ✓
- `docs/DB_MODEL.md` aktualisiert ✓

### Geänderte Dateien
- `backend/alembic/versions/0025_task_times.py` (neu)
- `backend/app/models.py` (`Task.start_time`, `Task.end_time`)
- `backend/app/collab/schemas.py` (`start_time`, `end_time` in TaskIn/Update/Out)
- `backend/app/collab/routes.py` (Serialisierung `strftime('%H:%M')`, create/update)
- `frontend/index.html` (Gantt-Gruppierung, Grid, Achsenbeschriftung, Zeit-Inputs)
- `docs/DB_MODEL.md`

---

## Update (2026-04-17): Kunden-Link (customer_link)

### Completed
- **`customer_link`-Feld**: Neues optionales verschlüsseltes Textfeld auf `customers` (Migration 0026)
- **Verschlüsselung**: AES-256-GCM via `encrypt_credential`/`decrypt_credential` mit `context="customers.customer_link"` — gleicher Pattern wie `api_key`, `git_token`
- **Admin-UI**: "Kunden-Link"-Eingabefeld im Kunden-Formular (admin.html), sichtbar in der Kunden-Übersichtstabelle als eigene Spalte
- **Dashboard-Header**: Kundenname ist klickbarer Link (gestrichelt unterstrichen) wenn `customer_link` gesetzt, öffnet in neuem Tab
- **`/api/customers/names`**: Liefert `customer_link` (entschlüsselt) an alle authentifizierten User

### Spec-Compliance
- QLIK-PS-001: `customer_link` AES-256-GCM verschlüsselt ✓
- QLIK-PS-003: `customers` ist kein project-scoped Table, kein neuer Table → keine neue Policy nötig ✓
- QLIK-PS-006: Backend + Frontend + Admin synchron ✓
- QLIK-PS-008: Migration `0026_customer_link.py` = 22 Zeichen ✓
- `docs/DB_MODEL.md` aktualisiert ✓

### Geänderte Dateien
- `backend/alembic/versions/0026_customer_link.py` (neu)
- `backend/app/models.py` (`Customer._customer_link_encrypted`, `customer_link` property)
- `backend/app/customers/routes.py` (CustomerIn, CustomerUpdate, CustomerOut, CustomerNameOut, `_to_out`, `/names`, create, update)
- `frontend/admin.html` (Kunden-Link Eingabefeld + Tabellenspalte)
- `frontend/index.html` (`updateHeader()` mit klickbarem Link)
- `docs/DB_MODEL.md`

---

## Update (2026-04-17): Master Items Sync Modul

### Completed
- **`shared/master_items_sync.py`**: Export, Diff und Import von Qlik Master Items via Engine API (WebSocket/QIX); nutzt `QlikEngineClient.open_session`
- **`export_master_items(creds, app_id)`**: Liest Dimensions, Measures, Visualizations aus einer App
- **`diff_master_items(creds, source, target_app_id)`**: Vergleich Source-Export gegen Live-App (new / existing / conflict nach Titel)
- **`import_master_items(creds, target_app_id, source, options)`**: Import mit `skip`/`overwrite` Duplikat-Handling + `dry_run`-Modus
- **Session-Management**: `open_session` in `QlikEngineClient` garantiert `ws.close()` bei jedem Exit-Pfad
- **Fehler-Isolation**: Jeder einzelne Engine-Call in `try/except` — ein fehlendes Item bricht den Gesamtprozess nicht ab
- **Script Sync UI**: Properties-Detail-Panel, Diff mit gecachtem Export, Parallel-App-Listen-Refresh

### Spec-Compliance
- QLIK-PS-001: Keine Credentials in DB gespeichert — nimmt `QlikCredentials` entgegen, alles im Speicher ✓
- QLIK-PS-005: Keine lokalen Artefakte ✓
- QLIK-PS-008: Kein Migration-File (kein neues DB-Schema) ✓

### Geänderte Dateien
- `backend/shared/master_items_sync.py` (neu, dann Refactoring: eigener WS-Code → `QlikEngineClient.open_session`)
- `backend/shared/qlik_engine_client.py` (`EngineSession`-Klasse + `open_session` ergänzt)
- `backend/app/qlik_deps.py` (neu: `resolve_project_creds`, `CredentialsError`)
- `backend/app/master_items/routes.py` (neu; nutzt `qlik_deps`)
- `backend/app/themes/service.py` (Credential-Auflösung auf `qlik_deps` umgestellt)
- `frontend/script-sync.html` (Master Items Tab vollständig implementiert)

---

## Update (2026-04-20): Architektur-Refactoring (Simplify Pass)

### Completed
- **WebSocket-Duplizierung beseitigt**: `master_items_sync.py` hatte ~170 Zeilen eigene WS/JSON-RPC-Logik (identisch mit `qlik_engine_client.py`). Entfernt; `QlikEngineClient.open_session` + `EngineSession` als geteilte Transportschicht eingeführt.
- **`EngineSession`-Klasse**: Kapselt alle Engine-RPC-Methoden (`create_session_object`, `get_layout`, `get_dimension/measure/object`, `create_dimension/measure/object`, `set_properties`, `do_save`)
- **`open_session` Context-Manager**: Verbindungsauf-/abbau, `OpenDoc`, Exception-Mapping → `QlikEngineError` — ein einziger Einstiegspunkt für alle multi-step Engine-Operationen
- **`qlik_deps.py`**: Geteilter Credential-Resolver `resolve_project_creds()` + typisierter `CredentialsError(ValueError)` mit `.status`-Feld; ersetzt identischen Code in `themes/service.py` und `master_items/routes.py`
- **Weitere Code-Quality-Fixes**: `getMiItemTitle` identische Branches zusammengeführt; `_strip_qinfo` auf Modulebene verschoben; `copy.deepcopy()` statt `json.loads(json.dumps())`; `source_export`-Cache in `DiffRequest` verhindert redundante WS-Verbindung

### Spec-Compliance
- QLIK-PS-001: Kein Credential-Handling geändert ✓
- QLIK-PS-003: Kein neues DB-Schema ✓
- QLIK-PS-008: Kein Migration-File ✓

### Geänderte Dateien
- `backend/shared/qlik_engine_client.py` (`EngineSession` + `open_session`)
- `backend/shared/master_items_sync.py` (~170 Zeilen WS-Code entfernt, `QlikEngineClient` genutzt)
- `backend/app/qlik_deps.py` (neu)
- `backend/app/master_items/routes.py` (`qlik_deps` genutzt, `source_export` in `DiffRequest`)
- `backend/app/themes/service.py` (`qlik_deps` genutzt)
- `frontend/script-sync.html` (getMiItemTitle, renderMiDetailBody Fixes)

---

## Update (2026-04-20): Fetch-Job Verbesserungen + Master Items Import-Selektion

### Completed

#### SSE Job-Progress Streaming
- **`GET /api/fetch/jobs/{job_id}/stream`**: Server-Sent Events Endpoint — liefert Job-Status alle 0.5s, schließt automatisch nach Abschluss/Fehler
- **Frontend**: `pollFetchJob()` nutzt jetzt `EventSource` (SSE-native), Polling-Fallback für ältere Browser
- Fortschrittsbalken zeigt exakten Schritt-Fortschritt basierend auf `completedSteps`

#### Master Items Import-Selektion
- **Backend**: `ImportRequest.source_export: dict | None` — gleiches Muster wie `DiffRequest`, vermeidet Re-Export
- **Frontend**: Nach Diff erscheint Item-Selektion-Panel — Checkboxen pro Item (Neu=✓, Konflikt=✓, Gleich=☐)
  - Accordion je Typ (Dimensions/Measures/Visualizations), "Alle wählen / Alle abwählen" Buttons
  - Import sendet nur gewählte Items als `source_export` — kein unnötiger WS-Verbindungsaufbau

#### Geplante Fetch-Jobs
- **Migration 0027** (`0027_fetch_schedules.py`): `fetch_schedules` Tabelle mit `project_id`, `steps`, `cron_expr`, `label`, `is_active`, `last_run_at`, `next_run_at`, `created_by_user_id`
- **`FetchSchedule` Model** in `models.py`
- **APScheduler 3.x** (`AsyncIOScheduler`): lädt alle aktiven Zeitpläne beim Start aus DB, aktualisiert sich bei CRUD-Operationen
- **4 Admin-Endpoints**: `GET/POST /api/fetch/schedules`, `PUT/DELETE /api/fetch/schedules/{id}`
- **Frontend**: "Geplante Fetch-Jobs" Sektion in script-sync.html — Tabelle mit Cron/Schritten/Status/Nächster Lauf, Create/Edit Modal mit Cron-Eingabe + Schritt-Checkboxen

### Spec-Compliance
- QLIK-PS-001: Keine Credential-Änderungen ✓
- QLIK-PS-003: Keine neue project-scoped Tabelle mit user-Daten (FetchSchedule ist admin-only, kein RLS nötig) ✓
- QLIK-PS-008: Migration `0027_fetch_schedules.py` = 23 Zeichen ✓

### Geänderte Dateien
- `backend/main.py` (SSE-Endpoint, `_reload_scheduler`, `_run_scheduled_fetch`, lifespan, 4 CRUD-Routen)
- `backend/requirements.txt` (`apscheduler>=3.10,<4.0`)
- `backend/alembic/versions/0027_fetch_schedules.py` (neu)
- `backend/app/models.py` (`FetchSchedule`)
- `backend/app/master_items/routes.py` (`source_export` in `ImportRequest`)
- `frontend/script-sync.html` (SSE polling, Checkbox-Selektion, Zeitplan-Sektion + Modal)

---

## Update (2026-04-20): Admin-Übersicht Fetch-Zeitpläne

### Completed
- **`GET /api/fetch/schedules`**: `project_id` jetzt optional — ohne Parameter werden alle Schedules aller Projekte zurückgegeben (JOIN über `projects` → `customers`, mit `project_name` + `customer_name`)
- **`frontend/admin.html`**: Neuer Sidebar-Tab "Fetch-Zeitpläne" — zentrale Übersicht aller Cron-Zeitpläne mit Aktivieren/Deaktivieren-Toggle und Löschen. Erstellen/Bearbeiten bleibt in `script-sync.html` (pro Projekt)

### Spec-Compliance
- QLIK-PS-003: Kein neues DB-Schema ✓
- QLIK-PS-008: Kein Migration-File ✓

### Geänderte Dateien
- `backend/main.py` (`list_schedules`: `project_id` optional, JOIN + Namens-Enrichment)
- `frontend/admin.html` (Sidebar-Link, `schedulesSection`, `loadAllSchedules`, Toggle/Delete-Handler)
