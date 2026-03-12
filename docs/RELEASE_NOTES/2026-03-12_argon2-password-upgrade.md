# 2026-03-12 Argon2 Password Upgrade

## Scope

- backend
- auth
- docs

## Summary

Upgraded password hashing to `Argon2id` while keeping legacy `PBKDF2-SHA256` hashes login-compatible.

## Implemented

- Updated `backend/app/auth/utils.py`
  - `CryptContext` now prefers `argon2`
  - legacy `pbkdf2_sha256` hashes stay verifiable
  - new helper returns an upgraded hash when a legacy password is verified successfully
- Updated `backend/app/auth/routes.py`
  - successful login now replaces a verified legacy `PBKDF2-SHA256` hash with a fresh `Argon2id` hash before commit
- Updated `backend/requirements.txt`
  - added Argon2 runtime dependency

## Tests

- Extended `backend/tests/test_auth_utils.py`
  - new passwords hash to `Argon2id`
  - legacy `PBKDF2-SHA256` hashes verify and return an Argon2 upgrade hash
- Extended `backend/tests/test_auth.py`
  - legacy user login upgrades the stored password hash to `Argon2id`

## Notes

- No DB schema change was required for this step.
- Existing users are migrated lazily on their next successful login.
