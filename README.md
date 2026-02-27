# Qlik Atlas

Containerized Qlik lineage application with FastAPI backend, PostgreSQL, nginx frontend, authentication, customer/project management, and DB-backed lineage runtime reads.

## Current Status

- Docker-based stack is runnable end-to-end (`db`, `backend`, `frontend`, optional `pgadmin`)
- Authentication and admin flows are available
- Customer credentials are stored encrypted in the database (AES-256-GCM)
- Runtime reads for dashboard/graph/inventory/spaces/data-connections/usage/scripts are DB-backed
- Fetch pipeline is DB-first (`Qlik API -> in-memory transform -> PostgreSQL`)
- Local fetch artifacts are no longer the application source of truth (optional debug mode only)

## Quick Start (Docker)

(Ich möchte an meinem qlik atlas projekt weiterarbeiten. Bitte zuerst AGENTS.md lesen, dann die zentrale private Bridge nutzen, Gateway anwenden und danach docs/INDEX.md + relevante Specs/Dokumente scannen und immer anwenden, bevor du loslegst.
)

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at least:

- `JWT_SECRET`
- `CREDENTIALS_AES256_GCM_KEY_B64`
- `CREDENTIALS_AES256_GCM_KEY_ID`

Optional (for real fetch jobs):

- `QLIK_TENANT_URL`
- `QLIK_API_KEY`

Generate a local AES-256-GCM key (PowerShell, correct format):

```powershell
python -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Important:

- `CREDENTIALS_AES256_GCM_KEY_B64` must decode to exactly 32 bytes
- Keep the AES key stable after customer credentials have been stored
- Do not use production secrets in local `.env`

### 2. Start the stack

```bash
docker compose up --build
```

This starts:

- `db` (PostgreSQL)
- `backend` (FastAPI, auto-migrations on startup)
- `frontend` (nginx SPA on port `4001`)
- `pgadmin` (optional, port `5050`)

### 3. Open the app

- App: `http://localhost:4001`
- pgAdmin (optional): `http://localhost:5050`

Default seeded admin user:

- Email: `admin@admin.de`
- Password: `admin123`

## Services and Ports

| Service | Port | Purpose |
|---|---:|---|
| `frontend` | `4001` | UI (nginx) |
| `backend` | `8000` | FastAPI API |
| `db` | `5432` | PostgreSQL (internal/docker network) |
| `pgadmin` | `5050` | Optional DB inspection UI |

## Architecture (Current)

### Data flow

1. Admin starts fetch job for a project
2. Backend loads encrypted Qlik credentials from the project's customer
3. Backend fetches Qlik data (spaces/apps/connections/lineage/usage)
4. Payloads are normalized in memory
5. Data is persisted to PostgreSQL
6. Frontend runtime endpoints read from PostgreSQL (RLS-scoped)

### Runtime source of truth

- UI-facing runtime data is PostgreSQL (not local JSON files)
- Local artifacts may still exist as optional debug outputs when explicitly enabled

Debug/compat mode for local fetch artifacts (default is off):

- `FETCH_WRITE_LOCAL_ARTIFACTS=true`

## Authentication and Authorization

### Auth endpoints

- `POST /api/auth/register`
- `POST /api/auth/login`

Frontend behavior:

- Access token stored in `localStorage` (`auth_access_token`)
- API calls use `Authorization: Bearer <token>`

### Admin-only areas (high level)

- Customer create/update/delete
- Fetch job start/list/logs
- Admin user assignment/management routes

## Row-Level Security (RLS)

PostgreSQL RLS is used for customer/project scoped access.

Implementation summary:

- App sets per-session DB context (`app.user_id`, `app.role`)
- PostgreSQL policies evaluate access using helper SQL functions
- Project-scoped runtime tables inherit visibility via `project_id`

This applies to core runtime tables including:

- `qlik_apps`
- `lineage_nodes`
- `lineage_edges`
- `qlik_spaces`
- `qlik_data_connections`
- `qlik_app_usage`
- `qlik_app_scripts`

## Key API Areas (Current)

### Runtime/UI reads (DB-backed)

- `GET /api/dashboard/stats`
- `GET /api/inventory`
- `GET /api/apps`
- `GET /api/spaces`
- `GET /api/data-connections`
- `GET /api/graph/all`
- `GET /api/graph/app/{app_id}`
- `GET /api/graph/node/{node_id}`
- `GET /api/app/{app_id}/usage`
- `GET /api/app/{app_id}/script`

### Fetch jobs

- `GET /api/fetch/status`
- `GET /api/fetch/jobs`
- `GET /api/fetch/jobs/{job_id}`
- `GET /api/fetch/jobs/{job_id}/logs`
- `POST /api/fetch/jobs`

## Development

### Useful Docker commands

Start / rebuild:

```bash
docker compose up --build
```

Restart backend after `.env` changes:

```bash
docker compose up -d --force-recreate backend
```

Logs:

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f db
```

Stop:

```bash
docker compose down
```

### Manual migrations (if needed)

```bash
cd backend
alembic upgrade head
```

### Upgrade Notes (after pulling changes)

Use this sequence after code/config changes to avoid testing stale containers:

1. Check local changes (`git status`) and keep/commit what you want to preserve.
2. Rebuild and restart the stack:
```bash
docker compose down
docker compose up --build
```
3. If you changed only `.env`, recreating the backend is usually enough:
```bash
docker compose up -d --force-recreate backend
```
4. Verify backend migrations completed in logs:
```bash
docker compose logs -f backend
```
5. Start a new fetch job from the UI if runtime data is empty (DB-backed runtime reads do not depend on old local artifacts).

## Security Notes

- `.env` is ignored by git; do not commit secrets
- `JWT_SECRET` should be a strong random value
- `CREDENTIALS_AES256_GCM_KEY_B64` is required before creating customers
- Changing the AES key later breaks decryption of existing stored credentials
- Use non-production/sanitized data in local development and agent sessions

## Troubleshooting

**"missing encryption key env var: CREDENTIALS_AES256_GCM_KEY_B64"**

- Add `CREDENTIALS_AES256_GCM_KEY_B64` and `CREDENTIALS_AES256_GCM_KEY_ID` to `.env`
- Recreate backend container:

```bash
docker compose up -d --force-recreate backend
```

**Customer creation still fails after setting `.env`**

- Check backend container env values:

```bash
docker compose exec backend sh -lc "env | grep CREDENTIALS_AES256_GCM"
```

**No data visible in dashboard/graph after startup**

- Start a new fetch job from the UI (data is DB-backed and may be empty initially)
- Check fetch job logs in UI or `docker compose logs -f backend`

**Ports already in use**

- Change port mappings in `docker-compose.yml` (`frontend`, `backend`, `pgadmin`)

## Documentation

Project docs are split between root status docs and `docs/`:

- `docs/INDEX.md`
- `docs/CONTEXT.md`
- `docs/RELEASE_NOTES/README.md`
- `REQUIREMENTS.md`
- `PROJECT_STATUS.md`
- `FIXES_APPLIED.md`

## Roadmap (remaining work)

- Improve fetch-job progress visibility/details in the UI
- Add/expand automated tests for DB-only runtime + fetch flows
- Harden auth/session features (refresh token lifecycle, rate limiting)
- Continue reducing optional local artifact fallback/debug paths
