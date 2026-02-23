# Implementation Requirements & Roadmap

## 1. Core Infrastructure ✅ (DONE)

- [x] Multi-container Docker Compose setup (db, backend, frontend)
- [x] PostgreSQL database with persistent volumes
- [x] FastAPI backend with async SQLAlchemy + asyncpg
- [x] Nginx frontend serving static SPA
- [x] Health checks on all services
- [x] Non-root users in containers
- [x] Multi-stage Docker builds (smaller images)
- [x] .gitignore protecting secrets
- [x] Environment variables for all configuration
- [x] Application accessible on port 4001

## 2. Authentication System ✅ (DONE)

- [x] User model in PostgreSQL (id, email, password_hash, is_active, created_at)
- [x] Password hashing with bcrypt
- [x] JWT token generation (HS256)
- [x] `/auth/register` endpoint with duplicate email check
- [x] `/auth/login` endpoint with credential validation
- [x] Frontend login page (form + submission)
- [x] Frontend register page (form + submission)
- [x] Token storage in localStorage (`auth_access_token`)
- [x] API fetch wrapper including Authorization header
- [x] Automatic redirect to login on 401 response
- [x] Test user seeding: `admin@admin.de` / `admin123`
- [x] Alembic migration for users table

## 3. Qlik Credentials Management (TO DO)

- [ ] Create `QlikCredentials` table in PostgreSQL
  - Fields: id, user_id (FK), tenant_url, api_key_encrypted, created_at, updated_at
- [ ] Encryption at rest: use db-specific encryption (pgcrypto or similar) or application-level (cryptography library)
- [ ] Admin UI page (`/admin/qlik-settings`) to input/update Qlik credentials
  - Form with Tenant URL and API Key fields
  - "Test connection" button to verify credentials before saving
  - Visual feedback (success/error)
- [ ] Backend endpoint `POST /admin/qlik/settings` to securely store credentials
- [ ] Backend endpoint `GET /admin/qlik/settings` to retrieve (without exposing key)
- [ ] Middleware to decrypt credentials when needed for fetcher operations

## 4. Database Schema for Lineage Data (TO DO)

Design tables to replace JSON file storage:

### 4.1 Core Entities
- [ ] `apps` table
  - id, name, space_id, import_timestamp, metadata (JSONB for flexibility)
- [ ] `spaces` table
  - id, name, import_timestamp
- [ ] `data_connections` table
  - id, name, type, import_timestamp, metadata (JSONB)

### 4.2 Lineage Nodes & Edges
- [ ] `lineage_nodes` table
  - id, app_id (FK), label, type (app/db/table/qvd/etc), subtype, group, layer, metadata (JSONB)
- [ ] `lineage_edges` table
  - id, source_node_id (FK), target_node_id (FK), relation (LOAD/STORE/DEPENDS), context (JSONB)

### 4.3 Usage / Audit Trail
- [ ] `app_usage` table
  - id, app_id (FK), user_id, last_accessed, usage_count, metadata (JSONB)

### 4.4 Fetch Jobs / History
- [ ] `fetch_jobs` table
  - id, user_id (FK), status, started_at, completed_at, results (JSONB)

## 5. Data Import & Persistence (TO DO)

- [ ] Replace JSON read/write in fetchers with DB operations
  - Modify `fetchers/fetch_apps.py` to write to `apps` table instead of JSON
  - Modify `fetchers/fetch_spaces.py` to write to `spaces` table
  - Modify `fetchers/fetch_lineage.py` to write to `lineage_nodes/edges` tables
  - Modify `fetchers/fetch_data_connections.py` to write to `data_connections` table
  - Modify `fetchers/fetch_usage.py` to write to `app_usage` table

- [ ] Migration script `backend/scripts/migrate_json_to_db.py`
  - Read existing JSON files from `backend/output/`
  - Parse and normalize data
  - Insert into PostgreSQL tables
  - Idempotent (safe to run multiple times)
  - Verify data integrity post-migration

## 6. Token Management (TO DO)

- [ ] Refresh token support
  - Modify `/auth/login` and `/auth/register` to return both `access_token` and `refresh_token`
  - New `/auth/refresh` endpoint to exchange refresh token for new access token
  - Store refresh tokens in DB (linked to user)
  - Set appropriate expiration times (access: 15 min, refresh: 7 days)

- [ ] Token revocation / logout
  - `POST /auth/logout` endpoint to invalidate refresh token
  - Optional: implement token blacklist table in DB

- [ ] Frontend token refresh logic
  - Detect 401 on API call
  - Attempt refresh using stored refresh_token
  - Retry original request if refresh succeeds
  - Redirect to login if refresh fails

## 7. Rate Limiting (TO DO)

- [ ] Add `slowapi` or similar rate limiting library to requirements.txt
- [ ] Apply rate limiter to auth endpoints:
  - `/auth/register` — max 5 attempts per IP per hour
  - `/auth/login` — max 10 attempts per IP per hour
- [ ] Return 429 (Too Many Requests) with retry-after header
- [ ] Optional: Redis backend for distributed rate limiting (if scaling needed)

## 8. Protected API Endpoints (TO DO)

- [ ] Create auth decorator/dependency to validate JWT on protected routes
- [ ] Protected routes:
  - All `/api/` endpoints should require valid token
  - Read endpoints (GET) can be public or token-required (decision needed)
  - Write/fetch endpoints (POST) must require token
  - Optional: role-based access control (admin vs user)

## 9. API Documentation (TO DO)

- [ ] Generate/update OpenAPI (Swagger) specification
  - Document all auth endpoints
  - Document protected endpoints with required headers
  - Add example request/response bodies
  - Describe error responses (401, 403, 429, 500, etc)

- [ ] Create `ENDPOINTS.md` or similar documentation
  - List all available endpoints by category
  - Required headers/authentication
  - Request/response schemas
  - Error codes and meanings

## 10. Frontend Pages (TO DO)

- [x] Login page (`/login.html`)
- [x] Register page (`/register.html`)
- [ ] Dashboard/home page (`/`)
  - Check if user is authenticated (look for token)
  - Show logout button
  - Display user email
  - Show message if no Qlik credentials configured
  - Link to admin settings

- [ ] Admin settings page (`/admin/qlik-settings`)
  - Form to input/update Qlik credentials (Tenant URL, API Key)
  - "Test Connection" button
  - "Save" button with confirmation
  - Show last update timestamp
  - Visual error/success feedback

- [ ] Lineage visualization page (optional MVP)
  - Show graph of nodes/edges (interactive or read-only initially)
  - Filter by app / space
  - Simple table view as alternative

## 11. Error Handling & Validation (TO DO)

- [ ] Input validation on all endpoints
  - Email format validation (already in auth schemas)
  - Password strength requirements (min length, complexity?)
  - Qlik URL format validation
  - API key non-empty validation

- [ ] Proper HTTP status codes and error responses
  - 400 Bad Request (validation errors)
  - 401 Unauthorized (missing/invalid token)
  - 403 Forbidden (insufficient permissions)
  - 404 Not Found
  - 409 Conflict (duplicate email on register)
  - 429 Too Many Requests (rate limit exceeded)
  - 500 Internal Server Error (with logging)

## 12. Testing (TO DO)

- [ ] Backend unit tests
  - Auth flow (register, login, refresh, logout)
  - Database operations
  - JWT token generation/validation
- [ ] Backend integration tests
  - Full auth flow with real DB
  - Protected endpoint access
  - Rate limiting
- [ ] Frontend tests (optional)
  - Login/register form handling
  - Token storage/retrieval
  - API error handling

## 13. DevOps / CI-CD (TO DO - Optional for MVP)

- [ ] Docker registry setup (push images to registry)
- [ ] Kubernetes deployment manifests (optional)
- [ ] GitHub Actions CI workflow
  - Lint Python code (pylint/flake8)
  - Run backend tests
  - Build & push Docker images
  - Deploy to staging/production
- [ ] Secrets management
  - Use `.env` locally
  - Use Docker secrets or external secret store in production

## 14. Production Readiness (TO DO)

- [ ] Security hardening
  - Set secure JWT_SECRET in production (strong random value)
  - Use HTTPS in production (nginx reverse proxy + SSL cert)
  - Set CORS properly (only allow frontend domain, not *)
  - SQL injection prevention (SQLAlchemy parameterized queries already used)
  - XSS prevention (nginx headers, CSP)
  - CSRF if applicable (form POST vs JSON)

- [ ] Logging & monitoring
  - Centralized logging (FastAPI logs to file or service)
  - Error tracking (Sentry or similar)
  - Basic Prometheus metrics (optional)

- [ ] Performance optimization
  - Database indexes on frequently queried columns (email, user_id, etc)
  - Connection pooling (already configured in SQLAlchemy)
  - Caching strategy for lineage data (optional)

- [ ] Backup & recovery
  - PostgreSQL backup strategy
  - Restore procedures documented

---

## Summary: Work Remaining

**High Priority (Core Functionality)**
1. Qlik credentials secure storage (UI + DB + encryption)
2. Database schema for lineage data
3. Convert fetchers to persist to DB
4. Protected API endpoints with JWT validation
5. Frontend dashboard + admin settings page

**Medium Priority (Completeness)**
6. Refresh tokens + logout
7. Rate limiting on auth endpoints
8. API documentation (OpenAPI)
9. Input validation & error handling

**Lower Priority (Polish/Scale)**
10. Testing suite
11. Frontend lineage visualization
12. Role-based access control (RBAC)
13. CI/CD pipeline
14. Production deployment

---

## Questions for User

1. **Qlik Credential Encryption**: Would you prefer:
   - Database-level encryption (pgcrypto)?
   - Application-level encryption (Python cryptography library)?
   - External key management (AWS KMS, etc)?

2. **Public vs Protected API**: Should lineage/app data endpoints be:
   - Public (anyone can read without auth)?
   - Protected (require login)?
   - Role-based (admin vs user views)?

3. **Frontend Scope**: For MVP, should we build:
   - Basic dashboard + login only?
   - Add admin settings for Qlik creds?
   - Include lineage visualization (graph/table)?

4. **Testing Requirements**: Do you want:
   - Unit tests for auth logic?
   - Integration tests with real DB?
   - Frontend tests?
   - All of the above?

5. **Deployment Target**: Will this run:
   - Locally (current Docker Compose)?
   - Kubernetes cluster?
   - Cloud (AWS/GCP/Azure)?
