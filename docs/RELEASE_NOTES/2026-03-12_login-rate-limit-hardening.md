# 2026-03-12 Login Rate Limit Hardening

## Scope

- backend
- auth
- docs

## Summary

Added brute-force protection to `POST /api/auth/login` with a small in-process limiter and auth audit logging.

## Implemented

- New backend helper in `backend/app/auth/rate_limit.py`
  - tracks failed login attempts by client IP and normalized email
  - default limits:
    - `AUTH_LOGIN_IP_LIMIT=10`
    - `AUTH_LOGIN_EMAIL_LIMIT=5`
    - `AUTH_LOGIN_WINDOW_SECONDS=3600`
    - `AUTH_LOGIN_LOCKOUT_SECONDS=900`
- Updated `backend/app/auth/routes.py`
  - login checks active IP/email lockouts before password verification
  - failed login attempts record against both scopes
  - successful login clears accumulated failure state for that IP/email
  - blocked logins return `429 Too Many Requests` with `Retry-After`
  - auth audit logs now emit for success, failure, and rate-limited login attempts

## Tests

- Extended `backend/tests/test_auth.py`
  - existing cookie login / refresh / logout flow still covered
  - new IP-based login lockout test
  - new email-based login lockout test across multiple IPs

## Notes

- The limiter is intentionally in-memory for the current single-backend deployment.
- Limiter state resets on backend restart and is not shared across multiple backend instances.
- No DB schema change was required for this step.
