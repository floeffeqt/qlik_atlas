"""Shared path setup and SQLite compatibility for all tests.

Ensures the backend package root is on sys.path regardless of whether
tests run locally (from repo root) or inside the Docker container
(where /app IS the backend directory).

Also patches PostgreSQL-specific types (JSONB, ARRAY) so that SQLite
can be used as an in-memory test database.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

_backend_dir = Path(__file__).resolve().parents[1]
_repo_root_backend = _backend_dir.parent / "backend"

# Docker: /app is the backend dir itself
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# Local: repo_root/backend needs to be on path
if _repo_root_backend.exists() and str(_repo_root_backend) not in sys.path:
    sys.path.insert(0, str(_repo_root_backend))

# ── SQLite compatibility: map JSONB -> JSON, ARRAY -> JSON ──
from sqlalchemy import JSON, Integer
from sqlalchemy.dialects import postgresql

postgresql.JSONB = JSON  # type: ignore[attr-defined]
postgresql.ARRAY = lambda *a, **kw: JSON()  # type: ignore[attr-defined,assignment]

# SQLite cannot autoincrement BIGINT PKs; patch affected columns to Integer
from app.models import (  # noqa: E402
    RefreshToken, AppDataMetadataSnapshot, AppDataMetadataField,
    AppDataMetadataTable, AppDataMetadataTableProfile,
    AppDataMetadataFieldProfile, AppDataMetadataFieldMostFrequent,
    AppDataMetadataFieldFrequencyDistribution,
)

for _model in [
    RefreshToken, AppDataMetadataSnapshot, AppDataMetadataField,
    AppDataMetadataTable, AppDataMetadataTableProfile,
    AppDataMetadataFieldProfile, AppDataMetadataFieldMostFrequent,
    AppDataMetadataFieldFrequencyDistribution,
]:
    for _col in _model.__table__.columns:
        if _col.primary_key and str(_col.type) == "BIGINT":
            _col.type = Integer()

# ── SQLite timezone fix: naive datetimes → UTC-aware on load ──
from sqlalchemy import event

@event.listens_for(RefreshToken, "load")
def _refresh_token_tz_fix(target, _context):
    for attr in ("expires_at", "revoked_at", "created_at"):
        val = getattr(target, attr, None)
        if isinstance(val, datetime) and val.tzinfo is None:
            setattr(target, attr, val.replace(tzinfo=timezone.utc))
