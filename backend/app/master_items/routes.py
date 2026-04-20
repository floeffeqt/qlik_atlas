"""Master Items Sync API — export, diff, import Qlik master items via Engine API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.utils import require_admin
from ..database import get_session
from ..qlik_deps import CredentialsError, resolve_project_creds
from shared.master_items_sync import (
    export_master_items,
    diff_master_items,
    import_master_items,
    MasterItemsSyncError,
)

router = APIRouter(prefix="/master-items", tags=["master-items"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    project_id: int
    app_id: str


class DiffRequest(BaseModel):
    project_id: int
    source_app_id: str
    target_app_id: str
    source_export: dict | None = None


class ImportRequest(BaseModel):
    project_id: int
    source_app_id: str
    target_app_id: str
    options: dict = {}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/export")
async def run_export(
    payload: ExportRequest,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Export all master items from a Qlik app via the Engine API."""
    try:
        creds = await resolve_project_creds(payload.project_id, session, admin["user_id"], admin.get("role", "admin"))
    except CredentialsError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    try:
        return await export_master_items(creds, payload.app_id)
    except MasterItemsSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}") from exc


@router.post("/diff")
async def run_diff(
    payload: DiffRequest,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Export source app and diff against target app."""
    try:
        creds = await resolve_project_creds(payload.project_id, session, admin["user_id"], admin.get("role", "admin"))
    except CredentialsError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    try:
        source = payload.source_export or await export_master_items(creds, payload.source_app_id)
        result = await diff_master_items(creds, source, payload.target_app_id)
        summary: dict[str, Any] = {}
        for t in ("dimensions", "measures", "visualizations"):
            summary[t] = {
                "new": len(result[t]["new"]),
                "existing": len(result[t]["existing"]),
                "conflict": len(result[t]["conflict"]),
                "items": result[t],
            }
        return {"source_app_id": payload.source_app_id, "target_app_id": payload.target_app_id, **summary}
    except MasterItemsSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Diff failed: {exc}") from exc


@router.post("/import")
async def run_import(
    payload: ImportRequest,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Export source app and import master items into target app."""
    try:
        creds = await resolve_project_creds(payload.project_id, session, admin["user_id"], admin.get("role", "admin"))
    except CredentialsError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    try:
        source = await export_master_items(creds, payload.source_app_id)
        return await import_master_items(creds, payload.target_app_id, source, payload.options)
    except MasterItemsSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}") from exc
