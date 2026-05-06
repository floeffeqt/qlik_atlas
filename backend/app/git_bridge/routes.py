"""Script-sync REST endpoints (admin-only)."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.utils import require_admin
from ..database import get_session, apply_rls_context
from ..models import (
    Customer,
    Project,
    QlikApp,
    QlikAppScript,
    ScriptDeployment,
    ScriptGitMapping,
)
from ..serialization import iso_or_empty
from . import service

logger = logging.getLogger("atlas.git.routes")

router = APIRouter(prefix="/script-sync", tags=["script-sync"])


# ── Dependency ──

async def _admin_session(
    session: AsyncSession = Depends(get_session),
    admin_user: dict = Depends(require_admin),
) -> tuple[AsyncSession, dict]:
    await apply_rls_context(session, admin_user["user_id"], admin_user.get("role", "admin"))
    return session, admin_user


# ── Pydantic schemas ──

class MappingIn(BaseModel):
    project_id: int
    app_id: str
    repo_identifier: str
    branch: str = "main"
    file_path: str


class MappingOut(BaseModel):
    project_id: int
    app_id: str
    repo_identifier: str
    branch: str
    file_path: str
    last_git_commit_sha: Optional[str]
    last_git_script_hash: Optional[str]
    last_qlik_script_hash: Optional[str]
    last_checked_at: Optional[str]
    created_at: str
    updated_at: str


class SyncStatusOut(BaseModel):
    status: str
    app_id: str
    app_name: Optional[str] = None
    repo_identifier: Optional[str] = None
    branch: Optional[str] = None
    file_path: Optional[str] = None
    git_commit_sha: Optional[str] = None
    git_script_hash: Optional[str] = None
    qlik_script_hash: Optional[str] = None
    last_checked_at: Optional[str] = None
    detail: Optional[str] = None


class DeploymentOut(BaseModel):
    id: int
    project_id: int
    app_id: str
    direction: str
    git_commit_sha: Optional[str]
    git_script_hash: Optional[str]
    qlik_script_hash: Optional[str]
    status: str
    triggered_by: Optional[int]
    version_message: Optional[str]
    error_detail: Optional[str]
    created_at: str


class VerifyAccessOut(BaseModel):
    accessible: bool
    repo_identifier: str
    provider: str


def _mapping_to_out(m: ScriptGitMapping) -> MappingOut:
    return MappingOut(
        project_id=m.project_id,
        app_id=m.app_id,
        repo_identifier=m.repo_identifier,
        branch=m.branch,
        file_path=m.file_path,
        last_git_commit_sha=m.last_git_commit_sha,
        last_git_script_hash=m.last_git_script_hash,
        last_qlik_script_hash=m.last_qlik_script_hash,
        last_checked_at=iso_or_empty(m.last_checked_at) if m.last_checked_at else None,
        created_at=iso_or_empty(m.created_at),
        updated_at=iso_or_empty(m.updated_at),
    )


def _deployment_to_out(d: ScriptDeployment) -> DeploymentOut:
    return DeploymentOut(
        id=d.id,
        project_id=d.project_id,
        app_id=d.app_id,
        direction=d.direction,
        git_commit_sha=d.git_commit_sha,
        git_script_hash=d.git_script_hash,
        qlik_script_hash=d.qlik_script_hash,
        status=d.status,
        triggered_by=d.triggered_by,
        version_message=d.version_message,
        error_detail=d.error_detail,
        created_at=iso_or_empty(d.created_at),
    )


# ── Mapping CRUD ──

@router.get("/mappings", response_model=list[MappingOut])
async def list_mappings(
    project_id: int = Query(...),
    deps: tuple = Depends(_admin_session),
):
    session, _ = deps
    result = await session.execute(
        select(ScriptGitMapping)
        .where(ScriptGitMapping.project_id == project_id)
        .order_by(ScriptGitMapping.app_id)
    )
    return [_mapping_to_out(m) for m in result.scalars()]


@router.post("/mappings", response_model=MappingOut, status_code=201)
async def create_mapping(
    payload: MappingIn,
    deps: tuple = Depends(_admin_session),
):
    session, _ = deps
    existing = await service.get_mapping(session, payload.project_id, payload.app_id)
    if existing:
        raise HTTPException(400, "Mapping already exists for this app. Use PUT to update.")

    mapping = ScriptGitMapping(
        project_id=payload.project_id,
        app_id=payload.app_id,
        repo_identifier=payload.repo_identifier,
        branch=payload.branch,
        file_path=payload.file_path,
    )
    session.add(mapping)
    await session.commit()
    await session.refresh(mapping)
    return _mapping_to_out(mapping)


@router.put("/mappings/{app_id}", response_model=MappingOut)
async def update_mapping(
    app_id: str,
    payload: MappingIn,
    deps: tuple = Depends(_admin_session),
):
    session, _ = deps
    mapping = await service.get_mapping(session, payload.project_id, app_id)
    if not mapping:
        raise HTTPException(404, "Mapping not found")

    mapping.repo_identifier = payload.repo_identifier
    mapping.branch = payload.branch
    mapping.file_path = payload.file_path
    await session.commit()
    await session.refresh(mapping)
    return _mapping_to_out(mapping)


@router.delete("/mappings/{app_id}", status_code=204)
async def delete_mapping(
    app_id: str,
    project_id: int = Query(...),
    deps: tuple = Depends(_admin_session),
):
    session, _ = deps
    mapping = await service.get_mapping(session, project_id, app_id)
    if not mapping:
        raise HTTPException(404, "Mapping not found")
    await session.delete(mapping)
    await session.commit()


# ── Sync status ──

@router.get("/status/{app_id}", response_model=SyncStatusOut)
async def get_sync_status(
    app_id: str,
    project_id: int = Query(...),
    deps: tuple = Depends(_admin_session),
):
    session, _ = deps
    # Load current Qlik script from DB
    qlik_row = await session.execute(
        select(QlikAppScript.script).where(
            QlikAppScript.project_id == project_id,
            QlikAppScript.app_id == app_id,
        )
    )
    qlik_script = qlik_row.scalar_one_or_none()

    # Load app name for display
    app_row = await session.execute(
        select(QlikApp.app_name).where(
            QlikApp.project_id == project_id,
            QlikApp.app_id == app_id,
        )
    )
    app_name = app_row.scalar_one_or_none()

    # Load mapping for repo info
    mapping = await service.get_mapping(session, project_id, app_id)

    try:
        result = await service.check_drift(session, project_id, app_id, qlik_script)
        await session.commit()
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Drift check failed for app %s", app_id)
        raise HTTPException(502, f"Git provider error: {exc}")

    result["app_name"] = app_name
    if mapping:
        result["repo_identifier"] = mapping.repo_identifier
        result["branch"] = mapping.branch
        result["file_path"] = mapping.file_path

    return SyncStatusOut(**result)


@router.get("/overview", response_model=list[SyncStatusOut])
async def get_sync_overview(
    project_id: int = Query(...),
    deps: tuple = Depends(_admin_session),
):
    """Return sync status for all mapped apps in a project."""
    session, _ = deps
    mappings_result = await session.execute(
        select(ScriptGitMapping).where(ScriptGitMapping.project_id == project_id)
    )
    mappings = list(mappings_result.scalars())
    if not mappings:
        return []

    # Batch-load app names for all mapped apps
    app_ids = [m.app_id for m in mappings]
    names_result = await session.execute(
        select(QlikApp.app_id, QlikApp.app_name).where(
            QlikApp.project_id == project_id,
            QlikApp.app_id.in_(app_ids),
        )
    )
    app_names = {row.app_id: row.app_name for row in names_result}

    results = []
    for mapping in mappings:
        qlik_row = await session.execute(
            select(QlikAppScript.script).where(
                QlikAppScript.project_id == project_id,
                QlikAppScript.app_id == mapping.app_id,
            )
        )
        qlik_script = qlik_row.scalar_one_or_none()

        try:
            status = await service.check_drift(
                session, project_id, mapping.app_id, qlik_script
            )
        except Exception as exc:
            logger.warning("Drift check failed for %s: %s", mapping.app_id, exc)
            status = {"status": "error", "app_id": mapping.app_id, "detail": str(exc)}

        status["app_name"] = app_names.get(mapping.app_id)
        status["repo_identifier"] = mapping.repo_identifier
        status["branch"] = mapping.branch
        status["file_path"] = mapping.file_path
        results.append(SyncStatusOut(**status))

    await session.commit()
    return results


# ── Deployment history ──

@router.get("/history/{app_id}", response_model=list[DeploymentOut])
async def get_deployment_history(
    app_id: str,
    project_id: int = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    deps: tuple = Depends(_admin_session),
):
    session, _ = deps
    result = await session.execute(
        select(ScriptDeployment)
        .where(
            ScriptDeployment.project_id == project_id,
            ScriptDeployment.app_id == app_id,
        )
        .order_by(ScriptDeployment.created_at.desc())
        .limit(limit)
    )
    return [_deployment_to_out(d) for d in result.scalars()]


# ── Verify Git access ──

@router.get("/verify-access", response_model=VerifyAccessOut)
async def verify_git_access(
    project_id: int = Query(...),
    repo_identifier: str = Query(...),
    deps: tuple = Depends(_admin_session),
):
    session, _ = deps
    try:
        customer = await service.get_customer_for_project(session, project_id)
        provider = service.build_provider(customer)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    try:
        accessible = await provider.verify_access(repo_identifier)
    finally:
        await provider.close()

    return VerifyAccessOut(
        accessible=accessible,
        repo_identifier=repo_identifier,
        provider=customer.git_provider or "unknown",
    )