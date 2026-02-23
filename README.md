# Qlik Atlas — Containerized Stack

## Overview
A containerized FastAPI backend + nginx frontend + PostgreSQL database stack for Qlik lineage exploration with authentication.

## Quick Start

### 1. Setup Environment
```bash
cp .env.example .env
# Edit .env if needed (defaults are safe for local dev)
```

### 2. Start Services
```bash
docker compose up --build
```

This will:
- Build & start PostgreSQL container (connected on Docker network)
- Build & start FastAPI backend (port 8000)
- Build & start nginx frontend (port **4001**)
- Run migrations automatically
- Seed test user: `admin@admin.de` / `admin123`

### 3. Access Application
Open browser: **http://localhost:4001**

Login with:
- Email: `admin@admin.de`
- Password: `admin123`

## Architecture

### Services
| Service | Port | Description |
|---------|------|-------------|
| **Frontend** | 4001 | nginx serving SPA, proxies /api to backend |
| **Backend** | 8000 | FastAPI + Uvicorn (async) |
| **Database** | 5432 | PostgreSQL 15 (internal only) |

### Key Technologies
- **Backend**: FastAPI, SQLAlchemy (async), asyncpg
- **Auth**: JWT (HS256) + bcrypt password hashing
- **Frontend**: Vanilla JS with localStorage for tokens
- **DB**: PostgreSQL with Alembic migrations
- **Docker**: Multi-stage builds, non-root users, health checks

## Authentication

### Endpoints
- `POST /auth/register` — Create new user
  - Body: `{ "email": "user@example.com", "password": "..." }`
  - Returns: `{ "access_token": "...", "token_type": "bearer" }`

- `POST /auth/login` — Login existing user
  - Body: `{ "email": "user@example.com", "password": "..." }`
  - Returns: `{ "access_token": "...", "token_type": "bearer" }`

### Frontend Integration
- Token stored in `localStorage` under key `auth_access_token`
- Automatic redirect to `/login.html` on 401
- All API requests include `Authorization: Bearer {token}` header

## Database Schema

### Users Table
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(320) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
```

## Development

### Run Migrations Manually
```bash
cd backend
alembic upgrade head
```

### Seed Database
```bash
cd backend
python -m scripts.seed_db
```

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

## Security Notes

- `.env` is in `.gitignore` — never commit secrets
- JWT_SECRET should be a strong random value in production
- Passwords hashed with bcrypt (cost factor 12 by default)
- Non-root users in all containers
- CORS configured for frontend origin
- Environment variables for all configuration

## Next Steps / Roadmap

- [ ] Admin UI for Qlik credential management (stored encrypted in DB)
- [ ] Refresh token support + token revocation
- [ ] Rate limiting on auth endpoints
- [ ] PostgreSQL schema for lineage data (apps, spaces, connections)
- [ ] Convert fetchers to write to DB instead of JSON
- [ ] Complete API documentation (Swagger/OpenAPI)
- [ ] Frontend pages for lineage visualization
- [ ] Tests & CI/CD


## Troubleshooting

**"Docker connection refused"**: Ensure Docker Desktop is running (Windows) or docker daemon is started

**"Port 4001 already in use"**: Change port in `docker-compose.yml` frontend service

**"Database connection failed"**: Check `DATABASE_URL` in `.env` matches postgres service credentials

**"Login fails"**: Ensure migrations ran (check logs: `docker compose logs backend`)

---

For detailed architecture discussions and implementation questions, see requirements section below.
# Lineage Explorer (Local-First)

This repository is intentionally reduced to:
- `backend/`
- `frontend/`
- `output/`

`./output` is the single source of truth for generated lineage artifacts.

## Run (Dev)

1. Backend (port `8000`)

```powershell
cd backend
python -m venv .venv
# activate .venv
python -m pip install -r requirements.txt

# backend-only Qlik credentials (required for fetch jobs)
$env:QLIK_TENANT_URL = "https://<tenant>.<region>.qlikcloud.com"
$env:QLIK_API_KEY = "<qlik_api_key>"

uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

2. Frontend (port `5173`)

```powershell
cd frontend
npm install
# optional override (default is http://127.0.0.1:8000)
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
npm run dev
```

## Run (Dev - CMD)

Use two separate CMD terminals.

1. Backend (CMD Terminal 1, port `8000`)

```cmd
cd C:\Users\MauriceOkoye\Desktop\Entwicklung\backend
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt

set QLIK_TENANT_URL=https://<tenant>.<region>.qlikcloud.com
set QLIK_API_KEY=<qlik_api_key>

python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

2. Frontend (CMD Terminal 2, port `5173`)

```cmd
cd C:\Users\MauriceOkoye\Desktop\Entwicklung\frontend
npm install
set VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

## API Expectations

Frontend uses backend HTTP endpoints only:
- `GET /api/apps`
- `GET /api/spaces`
- `GET /api/data-connections`
- `GET /api/graph/app/{appId}?depth=...`
- `GET /api/graph/node/{nodeId}?direction=...&depth=...`
- `GET /api/graph/all`
- `GET /api/app/{appId}/usage`
- `GET /api/app/{appId}/script`
- `GET /api/fetch/status`
- `GET /api/fetch/jobs`
- `GET /api/fetch/jobs/{jobId}`
- `POST /api/fetch/jobs`

No frontend token handling. No direct calls to Qlik Cloud from the frontend.

## Frontend Tabs

- `Datenfluss`: existing lineage explorer graph view.
- `Datenabzug`: starts backend fetch jobs in the correct order (spaces -> apps -> data-connections -> lineage -> app-edges -> usage), supports optional cleanup of old artifacts, and shows job status.
