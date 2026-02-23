# Build & Startup Issues - FIXED

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
