# Build & Startup Issues - FIXED

## [SECURITY] 2026-04-29 Stufe-1 Umgebungstrennung: getrennte Env-Dateien pro Deployment

- Area: docker-compose.yml, .gitignore, .env.*, docs/ENVIRONMENT.md
- Changes:
  1. `.env.dev` erstellt — Entwicklungsumgebung (im Repo, keine echten Secrets)
  2. `.env.prod` erstellt — Produktionsvorlage mit CHANGE_ME-Platzhaltern (nicht im Repo)
  3. `.gitignore`: `.env.prod` und `.env.staging` explizit ausgeschlossen
  4. `docker-compose.yml`: `env_file` auf `${ENV_FILE:-.env.dev}` umgestellt — Standard ist Dev, Prod via `ENV_FILE=.env.prod docker compose up -d`
  5. `.env.example` aktualisiert mit kritischem AES-Key-Hinweis
  6. `docs/ENVIRONMENT.md` erstellt — vollständige Doku inkl. ⚠️ KRITISCH-Abschnitt zu `CREDENTIALS_AES256_GCM_KEY_B64` (Rotation nur mit Re-Encryption, Backup-Pflicht im Passwort-Manager)
- Verification: `git ls-files .env.prod` → leer (nicht getrackt); docker-compose.yml yaml-valide

## [SECURITY] 2026-04-29 QLIK-PS-005: Persistence-Audit — nur PostgreSQL darf persistieren

- Spec: QLIK-PS-005
- Area: docker-compose.yml, backend/shared/utils.py, backend/exporters/
- Changes:
  1. `backend`-Service: Bind-Mount `./backend:/app` entfernt — Container läuft ausschließlich mit eingebautem Image-Stand; kein Host-Dateisystemzugriff mehr
  2. `pgadmin`-Service: `volumes: pgadmin_data` entfernt + `profiles: [dev]` gesetzt — pgAdmin startet nur explizit via `docker compose --profile dev up`, kein persistentes Volume außerhalb Postgres
  3. Top-Level-Volume `pgadmin_data` entfernt
  4. `backend/exporters/` (json_writer.py, manifest_writer.py, __init__.py) gelöscht — totes Code mit Datei-Schreib-Fähigkeit, nie aufgerufen
  5. `backend/shared/utils.py`: `write_json`, `read_json`, `write_csv`, `write_xlsx`, `ensure_dir`, `sanitize_name` entfernt — sämtliche Datei-Schreib-/Lese-Funktionen; einzig genutzte Funktion `url_encode_qri` bleibt
- Verification: `grep -rn "write_json\|write_csv\|write_xlsx\|ensure_dir\|read_json\|exporters"` → 0 Treffer im Produktiv-Code; docker-compose.yml syntaktisch valide
- Residual Risk: Bei Backend-Code-Änderungen muss neu gebaut werden (`docker compose up -d --build backend`)

## [BUGFIX] 2026-04-28 Lineage: Außerhalb-Filter entfernt Shared-Nodes fälschlicherweise

- Severity: medium
- Area: frontend/lineage.html
- Source: code-review / correctness audit
- Symptoms: Beim Ausblenden von Outside-Area-Apps wurden Table-/Field-Nodes, die
  sowohl mit einer Inside-Area-App als auch mit Outside-Area-Apps verbunden sind
  (Shared Sources), fälschlicherweise aus dem Graph entfernt.
- Root Cause: `collectIntermediateNodesBetweenOutsideApps` stellte die falsche Frage:
  „Liegt dieser Node auf einem Pfad zwischen zwei Outside-Apps?" statt
  „Ist dieser Node nach dem Entfernen der Outside-Apps noch von einer Inside-App
  erreichbar?" — führte zu O(V×(V+E))-Laufzeit und falschen Ergebnissen bei
  gemeinsam genutzten Datenquellen.
- Fix: Funktion `collectIntermediateNodesBetweenOutsideApps` entfernt. Ersetzt durch:
  1. Kanten zu Outside-Apps entfernen (cleanEdges)
  2. BFS via `collectReachableNodeIds` von allen Inside-Area-Apps auf cleanEdges
  3. Nodes, die nicht erreichbar sind, als Waisen ausblenden
  Komplexität: O(V+E) statt O(V×(V+E)); korrekt auch bei Shared Sources.
- Changed Files: frontend/lineage.html
- Verification: JS-Syntax-Check (node -e "new Function(...)") → pass; Docker rebuild → started clean
- Residual Risk: none

## [FEATURE] 2026-04-20 Admin-Übersicht Fetch-Zeitpläne

- Area: backend/main.py, frontend/admin.html
- Changes:
  1. `GET /api/fetch/schedules`: `project_id` optional — ohne Parameter alle Schedules via JOIN `projects` → `customers`, mit `project_name` + `customer_name`
  2. `admin.html`: Sidebar-Tab "Fetch-Zeitpläne" — Tabelle aller Zeitpläne, Aktivieren/Deaktivieren-Toggle (PUT), Löschen (DELETE), Reload-Button
- Changed Files: `backend/main.py`, `frontend/admin.html`
- Residual Risk: none

## [FEATURE] 2026-04-20 Fetch-Job SSE + Master Items Checkbox-Selektion + Geplante Fetch-Jobs

- Area: backend/main.py, frontend/script-sync.html, backend/app/master_items
- Changes:
  1. **SSE Progress Streaming**: `GET /api/fetch/jobs/{job_id}/stream` — Server-Sent Events statt 1.5s-Polling; Fallback auf XHR-Polling wenn EventSource nicht verfügbar
  2. **Master Items Checkbox-Selektion**: Nach Diff erscheint Item-Panel (Neu=✓, Konflikt=✓, Gleich=☐); Import sendet nur ausgewählte Items als `source_export` — kein Re-Export, keine zweite WS-Verbindung
  3. **Geplante Fetch-Jobs**: Migration 0027, FetchSchedule-Model, APScheduler AsyncIOScheduler, 4 CRUD-Endpoints, Frontend-UI mit Cron-Modal und Zeitplan-Tabelle
- Changed Files: `backend/main.py`, `backend/requirements.txt`, `backend/alembic/versions/0027_fetch_schedules.py`, `backend/app/models.py`, `backend/app/master_items/routes.py`, `frontend/script-sync.html`
- Residual Risk: APScheduler läuft im gleichen asyncio event loop — bei sehr langen CPU-bound Operationen könnte er blockieren (in der Praxis unkritisch da Fetch-Jobs I/O-bound sind)

## [REFACTOR] 2026-04-20 WebSocket-Duplizierung beseitigt + geteilter Credential-Resolver

- Area: backend/shared, backend/app/master_items, backend/app/themes
- Source: proactive simplify pass
- Changes:
  1. `master_items_sync.py` hatte ~170 Zeilen eigene WS/JSON-RPC-Logik (exakte Kopie von `qlik_engine_client.py`). Entfernt. `QlikEngineClient.open_session` + neue `EngineSession`-Klasse sind jetzt der einzige WS-Transportpfad.
  2. `EngineSession` kapselt alle Engine-RPC-Methoden; `open_session` garantiert sauberes `ws.close()` auf allen Exit-Pfaden.
  3. `qlik_deps.py` (neu): `resolve_project_creds()` + `CredentialsError(ValueError, status=int)` — ersetzt identischen Copy-paste-Code in `themes/service.py` und `master_items/routes.py`.
  4. `DiffRequest.source_export: dict | None` — Frontend sendet gecachtes `_miExportData`; spart eine WS-Verbindung pro Diff-Aufruf.
  5. `getMiItemTitle` identische branches zusammengeführt; `_strip_qinfo` auf Modulebene verschoben; `copy.deepcopy()` statt `json.loads(json.dumps())`.
- Changed Files: `backend/shared/qlik_engine_client.py`, `backend/shared/master_items_sync.py`, `backend/app/qlik_deps.py` (neu), `backend/app/master_items/routes.py`, `backend/app/themes/service.py`, `frontend/script-sync.html`
- Residual Risk: none

## [BUGFIX] 2026-04-20 Master Items mini-tabs overwrote page-level tab state

- Severity: medium
- Area: frontend/script-sync
- Source: proactive fix during Master Items implementation
- Symptoms: Clicking a mini-tab inside the Properties panel (Dimensionen / Kennzahlen / Visualisierungen) would deactivate the "Master Items" page-level tab and hide the entire tab content.
- Root Cause: Both page-level tabs and mini-tabs used the `.tab-btn` class. The page-level switcher used `querySelectorAll('.tab-btn')` which also matched mini-tabs. On mini-tab click it removed `active` from all `.tab-btn` (including the page-level one), then tried `getElementById('tab-' + null)` and threw an error.
- Fix: Scoped the page-level listener to `querySelectorAll('.tab-btn[data-tab]')` only. Mini-tabs use `data-mi-tab` and have a dedicated separate listener.
- Changed Files: `frontend/script-sync.html`
- Verification: Page-level tab switching and mini-tab switching work independently without interfering.
- Residual Risk: none

## [BUGFIX] 2026-04-20 scriptViewerPanel null crash on project change

- Severity: medium
- Area: frontend/script-sync
- Source: user-reported ("ich sehe nichts in script sync")
- Symptoms: Switching projects caused a TypeError because `document.getElementById('scriptViewerPanel')` returned `null` (element does not exist in this page's HTML) and the code called `.style.display` on it unconditionally.
- Root Cause: The `onProjectChanged` else-branch referenced an element from a different page version that was never added to `script-sync.html`.
- Fix: Added null guard: `var vp = document.getElementById('scriptViewerPanel'); if (vp) vp.style.display = 'none';`
- Changed Files: `frontend/script-sync.html`
- Verification: Project switching no longer throws; Script Sync tab renders correctly.
- Residual Risk: none

## [BUGFIX] 2026-04-09 Script viewer crashed with "Invalid group" for every app

- Severity: high
- Area: frontend/script-sync
- Source: user-reported
- Symptoms: Script Sync tab showed "Fehler: Invalid regular expression … Invalid group" for almost every app; no script content was rendered.
- Root Cause: `applyPlainHighlights` built a `RegExp` using `(?>…)` (PCRE atomic group syntax), which is not supported in JavaScript/V8 and throws a `SyntaxError`. The `new RegExp(…)` call was placed **outside** the surrounding `try/catch`, so the exception propagated instead of falling back to the `\b…\b` pattern.
- Fix: Moved `new RegExp(…)` inside the `try` block; removed the unsupported `(?>…)` wrapper (it was a performance hint only — not required for correctness).
- Changed Files: `frontend/script-sync.html`
- Verification: Manual smoke check — scripts render without error after hard-refresh; keyword highlighting (`LOAD`, `WHERE`, `HIERARCHYBELONGSTO`, …) confirmed working.
- Residual Risk: none

## [BUGFIX] 2026-04-09 Script viewer line numbers shifted after ///$tab section headers

- Severity: medium
- Area: frontend/script-sync
- Source: proactive bug-hunt
- Symptoms: After introducing `///$tab` section-header rendering, every script line number after a tab marker was off by 1 (or by the number of tab markers preceding it), because tab-header divs were not counted as a line.
- Root Cause: `renderHighlightedScript` skipped incrementing `lineNum` when emitting a `sv-tab-section` div, but `///$tab` lines do occupy a real line position in the Qlik script file.
- Fix: Added `lineNum++` after emitting the section-header div so subsequent line numbers stay consistent with the actual script.
- Changed Files: `frontend/script-sync.html`
- Verification: Manual smoke check with a script containing multiple `///$tab` markers confirmed that line numbers after each header are correct.
- Residual Risk: none

## [BUGFIX] 2026-03-12 JWT access token was exposed to page JavaScript via localStorage

- Severity: high
- Area: frontend/auth, backend/auth
- Source: proactive bug-hunt
- Symptoms: authenticated browser sessions kept the bearer token in `localStorage`, so any XSS-capable page script could read and exfiltrate the active JWT.
- Root Cause: the login flow returned the raw access token in the JSON response and frontend session handling persisted it in `localStorage` and forwarded it via `Authorization` headers.
- Fix: moved the access token transport to a backend-set `HttpOnly` auth cookie, added `/api/auth/logout` cookie clearing, allowed backend auth dependencies to resolve token from cookie or bearer header, and updated frontend auth helpers/pages to use cookie-based requests plus non-sensitive cached user metadata only.
- Changed Files: `backend/app/auth/routes.py`, `backend/app/auth/schemas.py`, `backend/app/auth/utils.py`, `backend/tests/test_auth.py`, `backend/tests/test_auth_utils.py`, `frontend/assets/atlas-shared.js`, `frontend/login.html`, `frontend/lineage.html`, `frontend/theme-builder.html`, `README.md`, `PROJECT_STATUS.md`, `REQUIREMENTS.md`
- Verification: Python compile check passed for changed backend auth files/tests; targeted `python -m pytest backend/tests/test_auth.py backend/tests/test_auth_utils.py` could not run locally because `pytest` is not installed in the host interpreter; container-based verification attempted after runtime refresh.
- Residual Risk: no refresh-token rotation or server-side token revocation exists yet; logout currently clears the cookie but does not invalidate already issued JWTs.

## [BUGFIX] 2026-03-05 AuthZ depended on JWT role claim without live DB revalidation

- Severity: high
- Area: backend/auth
- Source: user-reported
- Symptoms: role/deactivation changes (`users.role`, `users.is_active`) took effect only after JWT expiry; admin access could remain valid for token lifetime.
- Root Cause: `get_current_user` and `require_admin` trusted JWT claims directly and did not revalidate user state/role against DB per request.
- Fix: `get_current_user` now decodes JWT, then resolves user in DB and enforces `is_active`; returned role is DB-derived. `require_admin` continues to check `current_user.role`, now DB-backed.
- Changed Files: `backend/app/auth/utils.py`, `backend/tests/test_auth_utils.py`
- Verification: Python compile check passed; added unit tests for DB-role override, deactivated-user block, and admin rejection path.
- Residual Risk: full pytest run blocked in this session because `pytest` is not installed in local interpreter.

## [BUGFIX] 2026-03-04 Data-connections API leaked qConnectStatement to UI payloads

- Severity: critical
- Area: backend/api
- Source: user-reported
- Symptoms: `/api/data-connections` returned `qConnectStatement` values, exposing sensitive connection details/tokens in the UI/API response.
- Root Cause: runtime response builder copied `qConnectStatement` from JSON payload/DB column into outbound response objects.
- Fix: removed `qConnectStatement` from `load_data_connections_payload` responses; added ingestion-time sanitization so `qConnectStatement` is not persisted inside `qlik_data_connections.data` JSON while keeping dedicated column mapping for internal matching.
- Changed Files: backend/app/db_runtime_views.py, backend/main.py, backend/tests/test_db_runtime_views.py, backend/tests/test_ingestion_payload_columns.py
- Verification: added/updated unit tests to assert response exclusion and storage sanitization; Python compile check passed for changed files.
- Residual Risk: existing rows in `qlik_data_connections.data` may still contain historical `qConnectStatement` values until next fetch/upsert or explicit cleanup migration.

## [BUGFIX] 2026-03-04 Lineage database-source mapping created false multi-connections

- Severity: high
- Area: backend/lineage-runtime
- Source: user-reported
- Symptoms: `database` source nodes were connected to too many unrelated source targets, creating ambiguous and wrong lineage edges in the UI graph.
- Root Cause: connection-to-source inference used broad `db:<type>` group matching and linked one connection to all matching DB/Table nodes in a project, even when the result was ambiguous or when a more precise QRI match existed.
- Fix: hardened connection mapping rules in `db_runtime_views`: precise `qri:db` prefix matching now links connections to matching source nodes first; app-root QRI matches keep priority where available; broad group fallback is only used for unique candidates (prefer `db` node, fallback to single `table` node) and skips ambiguous matches.
- Changed Files: backend/app/db_runtime_views.py, backend/tests/test_db_runtime_views.py
- Verification: Python compile check passed for changed files; added/updated unit tests for priority and ambiguity handling in connection mapping.
- Residual Risk: automated test execution is blocked in this session because `pytest` and runtime deps (e.g. `sqlalchemy`) are not installed in the local interpreter.

## [BUGFIX] 2026-03-04 App metadata duplicate field_hash crash in snapshot insert

- Severity: high
- Area: backend/ingestion
- Source: user-reported
- Symptoms: Fetch-Job failed in DB store step with `duplicate key value violates unique constraint "app_data_metadata_fields_snapshot_id_field_hash_key"`.
- Root Cause: `app_data_metadata_fields` rows were bulk inserted without deduplication, while the upstream metadata payload can contain duplicate `field_hash` values within one snapshot.
- Fix: Added deterministic deduplication/merge logic for metadata fields by `field_hash` before insert; added key-based deduplication guards for other metadata child rows with unique constraints (`tables`, `table_profiles`, `field_profiles`, `field_most_frequent`, `field_frequency_distribution`).
- Changed Files: backend/main.py, backend/tests/test_ingestion_payload_columns.py
- Verification: Python compile check passed for changed files; added unit tests for dedupe/merge behavior (`_dedupe_app_data_metadata_field_rows`, `_dedupe_rows_by_key`).
- Residual Risk: full runtime validation in this session blocked because `pytest` is not installed in the local interpreter.

## Issues Found & Fixed

### 1. ✅ Port Configuration
- **Issue**: Frontend was on port 8080, requirement is 4001
- **Fix**: Updated `docker-compose.yml` port mapping: `4001:80`

### 2. ✅ Email Validation
- **Issue**: Pydantic `EmailStr` requires `email-validator` package, not installed
- **Fix**: Replaced with regex validation in `UserCreate` schema
- **Update**: No new dependencies needed; uses standard Python `re` module

### 3. ✅ Async SQLAlchemy Setup
- **Issue**: `sessionmaker` doesn't support async directly; need `async_sessionmaker`
- **Fix**: Updated `app/database.py` to use `async_sessionmaker` from `sqlalchemy.orm`
- **Added**: Connection pool pre-ping for better reliability

### 4. ✅ JWT Token Generation
- **Issue**: `datetime.utcnow()` deprecated; should use `datetime.now(timezone.utc)`
- **Fix**: Updated `app/auth/utils.py` to use timezone-aware datetime

### 5. ✅ Alembic Environment Setup
- **Issue**: Async engine setup incompatible with Alembic's sync approach
- **Fix**: Rewrote `alembic/env.py` to:
  - Use sync engine for migrations
  - Read `DATABASE_URL` from environment
  - Support both online and offline modes

### 6. ✅ Requirements Updates
- **Issue**: Missing dependencies for build; wrong versions
- **Fix**: Updated `requirements.txt`:
  - Added `SQLAlchemy[asyncio]` with version constraints
  - Fixed `asyncpg` version range
  - Removed unused `databases` package
  - Added proper version pins to avoid conflicts

### 7. ✅ Docker Build Chain
- **Issue**: Multi-stage Dockerfile missing `bash` and proper apt-get setup
- **Fix**: Updated frontend/backend Dockerfiles:
  - Added `bash` to runtime image (needed for `entrypoint.sh`)
  - Proper cleanup of apt cache
  - Fixed wheel directory handling
  - Correct pip install flags: `--find-links` instead of `-f`

### 8. ✅ Application Startup
- **Issue**: No automatic schema initialization or test user creation
- **Fix**: Created `backend/entrypoint.sh` that:
  - Waits for database to be ready
  - Runs `alembic upgrade head` (migrations)
  - Seeds test user via `scripts/seed_db.py`
  - Starts Uvicorn server
- **Updated**: Backend Dockerfile entrypoint now uses shell script

### 9. ✅ Test User Seeding
- **Issue**: No way to test auth without manually creating user
- **Fix**: Created `backend/scripts/seed_db.py`:
  - Creates tables if they don't exist (`Base.metadata.create_all`)
  - Creates test user: `admin@admin.de` / `admin123`
  - Idempotent: checks if user exists before creating
  - Runs automatically on startup via `entrypoint.sh`

### 10. ✅ Frontend API Proxy
- **Issue**: Nginx config used shell variable substitution which doesn't work
- **Fix**: Updated `frontend/nginx.conf`:
  - Hardcoded backend host as `http://backend:8000` (Docker DNS)
  - Added X-Forwarded headers for proper proxying

### 11. ✅ Python Module Init
- **Issue**: `app/auth/` might not be recognized as package
- **Fix**: Created `__init__.py` files:
  - `backend/app/auth/__init__.py`
  - `backend/scripts/__init__.py`

### 12. ✅ Alembic Configuration
- **Issue**: `alembic.ini` missing sqlalchemy.url configuration
- **Fix**: Added `sqlalchemy.url` entry to `alembic.ini`

### 13. ✅ Environment File
- **Issue**: `.env` didn't exist; Docker Compose failed
- **Fix**: Created `.env` with production-appropriate defaults:
  - Complex JWT_SECRET placeholder (must change in production)
  - Safe database credentials for local testing
  - Added `.env` to `.gitignore`

### 14. ✅ Documentation
- **Fix**: Updated `README.md` with:
  - Clear quickstart (3 simple steps)
  - Port 4001 highlighted
  - Test user credentials visible
  - Architecture overview
  - Auth endpoints documentation

## Files Modified/Created This Round

### Modified
- `docker-compose.yml` — removed version, changed port 8080→4001
- `backend/app/auth/schemas.py` — regex email validation
- `backend/app/database.py` — async_sessionmaker, connection pooling
- `backend/app/auth/utils.py` — timezone-aware datetime
- `backend/alembic/env.py` — rewritten for sync operations
- `backend/requirements.txt` — proper version constraints, removed unused
- `backend/Dockerfile` — added bash, proper entrypoint setup
- `frontend/nginx.conf` — hardcoded backend host, proper headers
- `backend/alembic.ini` — added sqlalchemy.url
- `README.md` — comprehensive quickstart

### Created
- `backend/entrypoint.sh` — startup script with migrations + seeding
- `backend/scripts/seed_db.py` — test user creation script
- `backend/app/auth/__init__.py` — package marker
- `backend/scripts/__init__.py` — package marker
- `.env` — local environment file
- `.gitignore` — protect secrets
- `REQUIREMENTS.md` — comprehensive roadmap

## Ready to Test

The stack is now ready for testing. Run:

```bash
docker compose up --build
```

Expected behavior:
1. **Database starts** — Postgres 15 ready in ~5 seconds
2. **Backend builds & starts**:
   - Creates all packages wheels
   - Installs dependencies
   - Waits for DB health check
   - Runs migrations (creates users table)
   - Seeds test user
   - FastAPI listening on port 8000
3. **Frontend starts** — nginx serving on port 4001
4. **All health checks pass** — services marked as healthy

### Access & Test

1. **Browser**: http://localhost:4001
2. **Login**: admin@admin.de / admin123
3. **Check backend**: http://localhost:8000/health (should show `{"status":"ok"...}`)
4. **Check logs**: `docker compose logs -f`

---

All code should now build and run without errors. If you encounter any issues, check:
- `docker compose logs backend` — for Python errors
- `docker compose logs db` — for database issues
- `docker compose logs frontend` — for nginx issues

---

## Additional Architecture Fixes (2026-02-25) - DB Runtime Source of Truth

### 15. ✅ Misleading Dashboard "Files loaded" metric replaced by DB metric
- **Issue**: Dashboard showed local artifact file count even when database was empty
- **Fix**:
  - `/api/dashboard/stats` now returns DB app count (`qlik_apps`) in the existing `filesLoaded` field (backward-compatible key)
  - Frontend label updated to **"Apps in DB"**

### 16. ✅ Legacy `GraphStore` runtime dependency removed
- **Issue**: Multiple user-facing read endpoints still depended on local files / in-memory `GraphStore`
- **Fix**:
  - Implemented DB-only runtime read layer
  - Removed `backend/fetchers/graph_store.py`

### 17. ✅ DB-only runtime reads for graph/inventory-adjacent endpoints
- **Migrated endpoints**:
  - `/api/inventory`, `/api/apps`
  - `/api/spaces`
  - `/api/data-connections`
  - `/api/graph/app/{app_id}`, `/api/graph/node/{node_id}`
  - `/api/reports/orphans`
  - `/api/app/{app_id}/usage`, `/api/app/{app_id}/script`
- **Note**: Local artifacts remain only as transitional fetch/import staging for DB persistence

### 18. ✅ DB schema extended for runtime-read completeness and graph linking
- **Added**:
  - `qlik_spaces`
  - `qlik_data_connections`
  - `qlik_app_usage`
  - `qlik_app_scripts`
  - `lineage_edges.app_id`
- **Added**: RLS policies for the new project-scoped tables

### 19. ✅ Fetch pipeline switched to DB-first (no local fetch artifacts by default)
- **Issue**: Fetch job still used local JSON files as the normal intermediate storage before DB persistence
- **Fix**:
  - Fetch steps now keep fetched payloads in memory and persist to PostgreSQL in the DB store step
  - Local fetch artifact writes are disabled by default (`FETCH_WRITE_LOCAL_ARTIFACTS=false`)
  - Optional compatibility/debug mode remains available via `FETCH_WRITE_LOCAL_ARTIFACTS=true`

## [BUGFIX] 2026-04-13 Task-Modal öffnet PUT statt POST nach Abbrechen

- Severity: medium
- Area: frontend/index.html
- Source: proactive bug-hunt
- Symptoms: Klickt der User "Abbrechen" im Task-Edit-Modal und öffnet danach "Neuer Task", wird `PUT /api/tasks/{id}` statt `POST /api/tasks` aufgerufen — der neue Task überschreibt den zuletzt bearbeiteten
- Root Cause: `_editTaskId` wurde in `closeTaskModal()` nicht zurückgesetzt; Variable blieb nach Abbrechen gesetzt
- Fix: `_editTaskId = null` am Ende von `closeTaskModal()` ergänzt
- Changed Files: frontend/index.html
- Verification: Code-Review der closeTaskModal-Funktion; logischer Flow geprüft
- Residual Risk: none
