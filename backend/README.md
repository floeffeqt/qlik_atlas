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
- `LINEAGE_DATA_DIR`: override data directory (default is `../output/lineage_success/` if it exists, else `data/lineage/`).
- `FRONTEND_DIST`: override frontend dist directory.
- `SPACES_FILE`: optional JSON file with space names (see format below).

Spaces file format (optional):
- Dict mapping: `{ "spaceId": "Space Name" }`
- Or list: `[{"spaceId":"...","spaceName":"..."}, {"id":"...","name":"..."}]`

## Fetch Pipeline (CLI)

From `backend/`:

1. `python fetch_spaces.py`
2. `python fetch_apps.py`
3. `python fetch_data_connections.py`
4. `python fetch_lineage.py`
5. `python fetch_usage.py`

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
- `APP_EDGES_OUTDIR` (optional CLI override, default `../output/lineage_success`)
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

`POST /api/fetch/jobs` always clears artifacts of the selected steps before starting, so only fresh run data is processed.

Notes:
- The main graph artifacts are `*__app_edges.json` in `output/lineage_success/`.
- `app-edges` are generated only for apps where the lineage extraction was successful for both `source` and `overview`.
