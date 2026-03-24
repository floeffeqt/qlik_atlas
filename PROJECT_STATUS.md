# Project Status: Implementation Summary

## ✅ What's Complete (Ready to Use)

### Infrastructure (100%)
- ✅ Docker Compose with 3 services: db, backend, frontend
- ✅ PostgreSQL 15 with persistent volumes
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
