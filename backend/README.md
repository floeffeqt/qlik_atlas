# Backend

**Run (Dev)**
1. `python -m venv .venv`
2. Activate venv.
3. `python -m pip install -r requirements.txt`
4. `uvicorn main:app --reload --host 127.0.0.1 --port 8000`

**Run (Prod)**
- `APP_ENV=prod uvicorn main:app --host 127.0.0.1 --port 8000`

Environment variables:
- `APP_ENV`: `dev` or `prod`.
- `FRONTEND_DIST`: override frontend dist directory.

## Fetch Pipeline (CLI)

Fuer den Runtime-Fetch nutze die Fetch Trigger API (oder den Frontend-Admin-Flow).

From `backend/` (example via API):

1. `uvicorn main:app --reload --host 127.0.0.1 --port 8000`
2. Trigger fetch job:
   - `curl -X POST "http://127.0.0.1:8000/api/fetch/jobs" -H "Authorization: Bearer <ADMIN_TOKEN>" -H "Content-Type: application/json" -d "{\"project_id\":1,\"steps\":[\"spaces\",\"apps\",\"data-connections\",\"lineage\",\"app-edges\",\"usage\"]}"`
3. Check status:
   - `curl -H "Authorization: Bearer <ADMIN_TOKEN>" "http://127.0.0.1:8000/api/fetch/jobs"`

Required environment variables for fetching:
- `QLIK_TENANT_URL`
- `QLIK_API_KEY`

Common optional variables:
- `FETCH_LIMIT_APPS` (empty = all apps)
- `FETCH_ONLY_SPACE`
- `FETCH_SPACES_LIMIT`
- `QLIK_TIMEOUT`
- `QLIK_MAX_RETRIES`
- `QLIK_LINEAGE_CONCURRENCY`
- `QLIK_USAGE_CONCURRENCY`
- `QLIK_USAGE_WINDOW_DAYS`
- `QLIK_APP_EDGES_UP_DEPTH` (default `-1` for full upstream lineage)
- `FETCH_TRIGGER_TOKEN` (optional: if set, `POST /api/fetch/jobs` requires `X-Fetch-Token`)

## Fetch Trigger API (for frontend)

- `GET /api/fetch/status`
- `GET /api/fetch/jobs`
- `GET /api/fetch/jobs/{jobId}`
- `POST /api/fetch/jobs`

Fetch steps can be selected from:
- `spaces`
- `apps`
- `data-connections`
- `lineage`
- `app-edges`
- `usage`

`POST /api/fetch/jobs` runs DB-first only: payloads are processed in-memory and persisted directly to PostgreSQL.

Notes:
- `app-edges` are generated only for apps where the lineage extraction was successful for both `source` and `overview`.
