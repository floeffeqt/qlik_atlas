from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger("atlas.api")

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from shared.config import is_prod, settings
from shared.models import GraphResponse, HealthResponse, InventoryResponse, OrphansReport, PaginatedGraphResponse
from shared.analytics_models import (
    AnalyticsAppFieldsResponse,
    AnalyticsAppTrendResponse,
    AnalyticsAreaAppsResponse,
    AnalyticsAreasResponse,
    BloatExplorerResponse,
    CostValueMapResponse,
    DataModelPackResponse,
    GovernanceOperationsResponse,
    LineageCriticalityResponse,
)
from app.auth.routes import router as auth_router
from app.customers.routes import router as customers_router
from app.auth.utils import get_current_user, get_current_user_id, require_admin
from app.database import get_session, apply_rls_context
from app.db_runtime_views import (
    load_app_script_payload,
    load_app_subgraph,
    load_app_usage_payload,
    load_data_connections_payload,
    load_graph_response,
    load_graph_response_paginated,
    load_inventory,
    load_node_subgraph,
    load_orphans_report,
    load_spaces_payload,
)
from app.analytics_runtime_views import (
    DEFAULT_DAYS as ANALYTICS_DEFAULT_DAYS,
    DEFAULT_FIELDS_LIMIT as ANALYTICS_DEFAULT_FIELDS_LIMIT,
    DEFAULT_GOVERNANCE_LIMIT as ANALYTICS_DEFAULT_GOVERNANCE_LIMIT,
    DataModelPackMetric,
    load_analytics_app_fields,
    load_analytics_app_trend,
    load_analytics_area_apps,
    load_analytics_areas,
    load_bloat_explorer,
    load_cost_value_map,
    load_data_model_pack,
    load_governance_operations,
    load_lineage_criticality,
)
from app.projects.routes import router as projects_router
from app.admin.routes import router as admin_router
from app.themes.routes import router as themes_router
from app.git_bridge.routes import router as git_bridge_router
from app.collab.routes import router as collab_router
from app.fetch_jobs.contracts import (
    FETCH_STEP_ALL_ORDER,
    INDEPENDENT_FETCH_STEPS,
    FetchJobRequest,
    FetchStep,
    _normalize_steps,
)
from app.fetch_jobs.runtime import (
    _run_app_data_metadata_step,
    _run_app_edges_step,
    _run_apps_step,
    _run_audits_step,
    _run_data_connections_step,
    _run_licenses_consumption_step,
    _run_licenses_status_step,
    _run_lineage_step,
    _run_reloads_step,
    _run_scripts_step,
    _run_spaces_step,
    _run_usage_step,
)
from app.fetch_jobs.store import _run_db_store_step
from shared.security_headers import apply_security_headers


app = FastAPI(title="Lineage Explorer API", docs_url=None, redoc_url=None)
app.include_router(auth_router, prefix="/api")
app.include_router(customers_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(themes_router, prefix="/api")
app.include_router(git_bridge_router, prefix="/api")
app.include_router(collab_router, prefix="/api")

# CORS
origins = settings.dev_cors_origins or []
origins.append(settings.connect_src)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(set(origins)),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


fetch_jobs_registry: dict[str, dict[str, Any]] = {}
fetch_jobs_lock = asyncio.Lock()
job_logs: dict[str, list[str]] = {}
MAX_FINISHED_JOBS = 50


async def _session_with_rls_context(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> AsyncSession:
    await apply_rls_context(session, current_user["user_id"], current_user.get("role", "user"))
    return session


async def _admin_session_with_rls_context(
    session: AsyncSession = Depends(get_session),
    admin_user: dict = Depends(require_admin),
) -> AsyncSession:
    await apply_rls_context(session, admin_user["user_id"], admin_user.get("role", "admin"))
    return session


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def _load_graph_from_db(
    session: AsyncSession,
    *,
    project_id: int | None = None,
) -> GraphResponse:
    """DB-backed graph read used by UI-facing lineage endpoints (RLS applies via session context)."""
    return await load_graph_response(session, project_id=project_id)


def _prune_old_jobs() -> None:
    """Remove oldest finished jobs when registry exceeds MAX_FINISHED_JOBS. Must be called under fetch_jobs_lock."""
    finished = [
        (jid, j) for jid, j in fetch_jobs_registry.items()
        if j.get("status") in {"completed", "failed"}
    ]
    if len(finished) <= MAX_FINISHED_JOBS:
        return
    finished.sort(key=lambda x: x[1].get("finishedAt", ""))
    to_remove = finished[:len(finished) - MAX_FINISHED_JOBS]
    for jid, _ in to_remove:
        del fetch_jobs_registry[jid]
        job_logs.pop(jid, None)


async def _append_log(job_id: str, msg: str) -> None:
    async with fetch_jobs_lock:
        if job_id in job_logs:
            job_logs[job_id].append(f"[{_utc_now_iso()}] {msg}")


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def _assert_fetch_token(token: str | None) -> None:
    required = settings.fetch_trigger_token
    if required and token != required:
        raise HTTPException(status_code=403, detail="invalid fetch trigger token")


async def _update_job(job_id: str, **values: Any) -> None:
    async with fetch_jobs_lock:
        job = fetch_jobs_registry.get(job_id)
        if not job:
            return
        job.update(values)
        job["updatedAt"] = _utc_now_iso()


async def _complete_job_step(job_id: str, step: FetchStep, result: dict[str, Any]) -> None:
    async with fetch_jobs_lock:
        job = fetch_jobs_registry.get(job_id)
        if not job:
            return
        completed = job.get("completedSteps", [])
        completed.append(step)
        job["completedSteps"] = completed
        results = job.get("results", {})
        results[step] = result
        job["results"] = results
        job["currentStep"] = None
        job["updatedAt"] = _utc_now_iso()


async def _execute_fetch_job(
    job_id: str,
    request: FetchJobRequest,
    steps: list[FetchStep],
    actor_user_id: int,
    actor_role: str,
) -> None:
    project_id = request.project_id
    apps_cache: list[dict[str, Any]] | None = None
    spaces_cache: list[dict[str, Any]] | None = None
    data_connections_cache: list[dict[str, Any]] | None = None
    reloads_cache: list[dict[str, Any]] | None = None
    audits_cache: list[dict[str, Any]] | None = None
    licenses_consumption_cache: list[dict[str, Any]] | None = None
    licenses_status_cache: list[dict[str, Any]] | None = None
    app_data_metadata_cache: list[dict[str, Any]] | None = None
    scripts_cache: list[dict[str, Any]] | None = None
    lineage_payloads_cache: list[dict[str, Any]] = []
    usage_payloads: list[dict[str, Any]] = []
    app_edges_payloads: list[dict[str, Any]] = []
    step_labels: dict[str, str] = {
        "spaces": "Spaces laden",
        "apps": "Apps laden",
        "data-connections": "Datenverbindungen laden",
        "reloads": "Reloads laden",
        "audits": "Audits laden",
        "licenses-consumption": "License Consumption laden",
        "licenses-status": "License Status laden",
        "app-data-metadata": "App Data Metadata laden",
        "scripts": "Scripts laden",
        "lineage": "Lineage berechnen",
        "app-edges": "App-Kanten berechnen",
        "usage": "Usage-Daten laden",
    }
    try:
        await _update_job(job_id, status="running")
        await _append_log(job_id, f"Job gestartet · {len(steps)} Schritt(e) geplant")

        await _append_log(job_id, f"Lade Credentials für Projekt {project_id}…")
        creds = await _load_project_creds(project_id, actor_user_id=actor_user_id, actor_role=actor_role)
        await _append_log(job_id, "✓ Credentials geladen")

        cleared = {
            "files": [],
            "dirs": [],
            "skipped": True,
            "reason": "local artifacts removed (DB-first-only runtime)",
        }
        await _append_log(job_id, "Lokale Fetch-Artefakte sind entfernt (DB-first-only Runtime).")
        await _update_job(job_id, cleanup=cleared)

        step_positions: dict[FetchStep, int] = {step: i for i, step in enumerate(steps, 1)}

        async def _run_single_step(step: FetchStep, *, parallel: bool = False) -> None:
            nonlocal apps_cache
            nonlocal spaces_cache
            nonlocal data_connections_cache
            nonlocal reloads_cache
            nonlocal audits_cache
            nonlocal licenses_consumption_cache
            nonlocal licenses_status_cache
            nonlocal app_data_metadata_cache
            nonlocal scripts_cache
            nonlocal lineage_payloads_cache
            nonlocal app_edges_payloads
            nonlocal usage_payloads

            label = step_labels.get(step, step)
            prefix = "Parallel " if parallel else ""
            await _append_log(job_id, f"{prefix}Schritt {step_positions[step]}/{len(steps)}: {label}...")
            await _update_job(job_id, currentStep=step)

            if step == "spaces":
                spaces_cache, result = await _run_spaces_step(creds)
                await _append_log(job_id, f"✓ {result.get('count', 0)} Spaces geladen")
            elif step == "apps":
                apps_cache, result = await _run_apps_step(request, creds)
                await _append_log(job_id, f"✓ {result.get('count', 0)} Apps geladen")
            elif step == "data-connections":
                data_connections_cache, result = await _run_data_connections_step(creds)
                await _append_log(job_id, f"✓ {result.get('count', 0)} Datenverbindungen geladen")
            elif step == "reloads":
                reloads_cache, result = await _run_reloads_step(creds)
                await _append_log(job_id, f"Reloads geladen: {result.get('count', 0)}")
            elif step == "audits":
                audits_cache, result = await _run_audits_step(creds)
                await _append_log(job_id, f"Audits geladen: {result.get('count', 0)}")
            elif step == "licenses-consumption":
                licenses_consumption_cache, result = await _run_licenses_consumption_step(creds)
                await _append_log(job_id, f"License Consumption geladen: {result.get('count', 0)}")
            elif step == "licenses-status":
                licenses_status_cache, result = await _run_licenses_status_step(creds)
                await _append_log(job_id, f"License Status geladen: {result.get('count', 0)}")
            elif step == "app-data-metadata":
                if apps_cache is None:
                    raise RuntimeError("apps step data missing in DB-first mode; include 'apps' before 'app-data-metadata'")
                app_data_metadata_cache, result = await _run_app_data_metadata_step(apps_cache, creds)
                await _append_log(
                    job_id,
                    f"App Data Metadata geladen: {result.get('success', 0)} erfolgreich, {result.get('failed', 0)} fehlgeschlagen",
                )
            elif step == "scripts":
                if apps_cache is None:
                    raise RuntimeError("apps step data missing in DB-first mode; include 'apps' before 'scripts'")
                scripts_cache, result = await _run_scripts_step(apps_cache, creds)
                await _append_log(
                    job_id,
                    f"Scripts geladen: {result.get('success', 0)} erfolgreich, {result.get('failed', 0)} fehlgeschlagen",
                )
            elif step == "lineage":
                if apps_cache is None:
                    raise RuntimeError("apps step data missing in DB-first mode; include 'apps' before 'lineage'")
                lineage_payloads_cache, result = await _run_lineage_step(request, apps_cache, creds)
                await _append_log(job_id, f"✓ Lineage für {len(apps_cache)} Apps berechnet")
            elif step == "app-edges":
                if apps_cache is None:
                    raise RuntimeError("apps step data missing in DB-first mode; include 'apps' before 'app-edges'")
                app_edges_payloads, result = await _run_app_edges_step(
                    request,
                    apps_cache,
                    creds,
                    lineage_payloads=lineage_payloads_cache,
                )
                edges = result.get("appEdges", {}).get("edges", 0)
                await _append_log(
                    job_id,
                    f"✓ {edges} App-Kanten gefunden (Lineage-Level: {request.lineageLevel})",
                )
            elif step == "usage":
                if apps_cache is None:
                    raise RuntimeError("apps step data missing in DB-first mode; include 'apps' before 'usage'")
                usage_payloads, result = await _run_usage_step(request, apps_cache, creds)
                await _append_log(job_id, f"✓ Usage-Daten geladen")
            else:
                return

            await _complete_job_step(job_id, step, result)

        independent_steps = [step for step in steps if step in INDEPENDENT_FETCH_STEPS]
        if independent_steps:
            try:
                independent_limit = max(1, int(os.getenv("FETCH_INDEPENDENT_PARALLELISM", "3")))
            except (TypeError, ValueError):
                independent_limit = 3

            await _append_log(
                job_id,
                f"Starte {len(independent_steps)} unabhaengige Schritte parallel (max concurrency={independent_limit})...",
            )
            semaphore = asyncio.Semaphore(independent_limit)

            async def _run_parallel_step(step: FetchStep) -> None:
                async with semaphore:
                    await _run_single_step(step, parallel=True)

            await asyncio.gather(*[_run_parallel_step(step) for step in independent_steps])

        for step in steps:
            if step in INDEPENDENT_FETCH_STEPS:
                continue
            await _run_single_step(step)

        await _append_log(job_id, "Speichere Daten in Datenbank…")
        db_result = await _run_db_store_step(
            project_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            apps_data=apps_cache,
            spaces_data=spaces_cache,
            data_connections_data=data_connections_cache,
            reloads_data=reloads_cache,
            audits_data=audits_cache,
            licenses_consumption_data=licenses_consumption_cache,
            licenses_status_data=licenses_status_cache,
            app_data_metadata_data=app_data_metadata_cache,
            scripts_data=scripts_cache,
            usage_payloads=usage_payloads,
            app_edges_payloads=app_edges_payloads,
        )
        await _append_log(
            job_id,
            f"✓ Gespeichert: {db_result.get('apps', 0)} Apps · "
            f"{db_result.get('nodes', 0)} Knoten · {db_result.get('edges', 0)} Kanten · "
            f"{db_result.get('scripts', 0)} Scripts · "
            f"{db_result.get('reloads', 0)} Reloads · {db_result.get('audits', 0)} Audits · "
            f"{db_result.get('licenseConsumption', 0)} License-Consumption · "
            f"{db_result.get('licenseStatus', 0)} License-Status · "
            f"{db_result.get('appDataMetadataSnapshots', 0)} App-Data-Metadata-Snapshots"
        )
        await _append_log(job_id, "✓ Job erfolgreich abgeschlossen")
        await _update_job(job_id, status="completed", finishedAt=_utc_now_iso(), currentStep=None, dbStore=db_result)
    except Exception as exc:
        logger.exception("Fetch job %s failed", job_id)
        await _append_log(job_id, f"✗ Fehler: {exc}")
        await _update_job(
            job_id,
            status="failed",
            error=str(exc),
            finishedAt=_utc_now_iso(),
            currentStep=None,
        )


async def _load_project_creds(project_id: int, *, actor_user_id: int, actor_role: str) -> "QlikCredentials":
    """Load and return credentials from a project's customer — never stored in os.environ."""
    from app.database import AsyncSessionLocal
    from app.models import Customer, Project
    from shared.qlik_client import QlikCredentials
    from sqlalchemy import select
    async with AsyncSessionLocal() as session:
        await apply_rls_context(session, actor_user_id, actor_role)
        proj_result = await session.execute(select(Project).where(Project.id == project_id))
        project = proj_result.scalar_one_or_none()
        if not project:
            raise RuntimeError(f"project {project_id} not found")
        cust_result = await session.execute(select(Customer).where(Customer.id == project.customer_id))
        customer = cust_result.scalar_one_or_none()
        if not customer:
            raise RuntimeError(f"customer {project.customer_id} not found for project {project_id}")
        tenant_url = customer.tenant_url
        api_key = customer.api_key
        logger.info("Loaded credentials for project %s from customer '%s'", project_id, customer.name)
        return QlikCredentials(tenant_url=tenant_url, api_key=api_key)



@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app.router.lifespan_context = lifespan


@app.middleware("http")
async def log_and_secure(request: Request, call_next):
    response = await call_next(request)
    client = request.client.host if request.client else "-"
    print(f"{client} {request.url.path}")
    apply_security_headers(response, settings.connect_src)
    return response


@app.get("/api/health", response_model=HealthResponse)
async def api_health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        filesLoaded=0,
        nodesCount=0,
        edgesCount=0,
    )


@app.get("/api/dashboard/stats", response_model=HealthResponse)
async def dashboard_stats(
    project_id: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(_session_with_rls_context),
) -> HealthResponse:
    """Authenticated dashboard stats with DB-backed app/node/edge counts (RLS-scoped)."""
    from app.models import QlikApp, LineageNode, LineageEdge

    apps_stmt = select(sa_func.count()).select_from(QlikApp)
    nodes_stmt = select(sa_func.count()).select_from(LineageNode)
    edges_stmt = select(sa_func.count()).select_from(LineageEdge)
    if project_id is not None:
        apps_stmt = apps_stmt.where(QlikApp.project_id == project_id)
        nodes_stmt = nodes_stmt.where(LineageNode.project_id == project_id)
        edges_stmt = edges_stmt.where(LineageEdge.project_id == project_id)
    apps_result = await session.execute(apps_stmt)
    nodes_result = await session.execute(nodes_stmt)
    edges_result = await session.execute(edges_stmt)
    return HealthResponse(
        status="ok",
        filesLoaded=int(apps_result.scalar() or 0),  # backward-compatible field name; DB metric for dashboard UI
        nodesCount=int(nodes_result.scalar() or 0),
        edgesCount=int(edges_result.scalar() or 0),
    )


@app.get("/api/inventory", response_model=InventoryResponse)
async def inventory(session: AsyncSession = Depends(_session_with_rls_context)) -> InventoryResponse:
    return await load_inventory(session)


@app.get("/api/apps", response_model=InventoryResponse)
async def apps(session: AsyncSession = Depends(_session_with_rls_context)) -> InventoryResponse:
    return await load_inventory(session)


@app.get("/api/data-connections")
async def data_connections(session: AsyncSession = Depends(_session_with_rls_context)):
    try:
        return await load_data_connections_payload(session)
    except Exception:
        logger.exception("data connections query failed")
        raise HTTPException(status_code=500, detail="data connections query failed")


@app.get("/api/spaces")
async def spaces(session: AsyncSession = Depends(_session_with_rls_context)):
    return await load_spaces_payload(session)


def _analytics_error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


@app.get("/api/analytics/areas", response_model=AnalyticsAreasResponse)
async def analytics_areas(
    project_id: int | None = Query(default=None, ge=1),
    days: int = Query(default=ANALYTICS_DEFAULT_DAYS, ge=1, le=3650),
    session: AsyncSession = Depends(_session_with_rls_context),
) -> AnalyticsAreasResponse:
    try:
        payload = await load_analytics_areas(session, project_id=project_id, days=days)
    except Exception as exc:
        logger.exception("analytics areas query failed")
        raise HTTPException(
            status_code=500,
            detail=_analytics_error_detail(
                "analytics_areas_query_failed",
                "Bereiche konnten nicht geladen werden.",
            ),
        ) from exc
    return AnalyticsAreasResponse.model_validate(payload)


@app.get("/api/analytics/areas/{area_key:path}/apps", response_model=AnalyticsAreaAppsResponse)
async def analytics_area_apps(
    area_key: str,
    project_id: int | None = Query(default=None, ge=1),
    days: int = Query(default=ANALYTICS_DEFAULT_DAYS, ge=1, le=3650),
    session: AsyncSession = Depends(_session_with_rls_context),
) -> AnalyticsAreaAppsResponse:
    try:
        payload = await load_analytics_area_apps(
            session,
            area_key=area_key,
            project_id=project_id,
            days=days,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_analytics_error_detail("invalid_area_key", str(exc)),
        )
    except Exception as exc:
        logger.exception("analytics area apps query failed")
        raise HTTPException(
            status_code=500,
            detail=_analytics_error_detail(
                "analytics_area_apps_query_failed",
                "Apps im Bereich konnten nicht geladen werden.",
            ),
        ) from exc
    return AnalyticsAreaAppsResponse.model_validate(payload)


@app.get("/api/analytics/apps/{app_id:path}/fields", response_model=AnalyticsAppFieldsResponse)
async def analytics_app_fields(
    app_id: str,
    project_id: int = Query(..., ge=1),
    limit: int = Query(default=ANALYTICS_DEFAULT_FIELDS_LIMIT, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="byte_size"),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    search: str | None = Query(default=None),
    session: AsyncSession = Depends(_session_with_rls_context),
) -> AnalyticsAppFieldsResponse:
    try:
        payload = await load_analytics_app_fields(
            session,
            project_id=project_id,
            app_id=app_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_dir=sort_dir,
            search=search,
        )
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=_analytics_error_detail("app_not_found", "App nicht gefunden."),
        )
    except Exception as exc:
        logger.exception("analytics app fields query failed")
        raise HTTPException(
            status_code=500,
            detail=_analytics_error_detail(
                "analytics_app_fields_query_failed",
                "Felder konnten nicht geladen werden.",
            ),
        ) from exc
    return AnalyticsAppFieldsResponse.model_validate(payload)


@app.get("/api/analytics/apps/{app_id:path}/trend", response_model=AnalyticsAppTrendResponse)
async def analytics_app_trend(
    app_id: str,
    project_id: int = Query(..., ge=1),
    days: int = Query(default=ANALYTICS_DEFAULT_DAYS, ge=1, le=3650),
    session: AsyncSession = Depends(_session_with_rls_context),
) -> AnalyticsAppTrendResponse:
    try:
        payload = await load_analytics_app_trend(
            session,
            project_id=project_id,
            app_id=app_id,
            days=days,
        )
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=_analytics_error_detail("app_not_found", "App nicht gefunden."),
        )
    except Exception as exc:
        logger.exception("analytics app trend query failed")
        raise HTTPException(
            status_code=500,
            detail=_analytics_error_detail(
                "analytics_app_trend_query_failed",
                "Trenddaten konnten nicht geladen werden.",
            ),
        ) from exc
    return AnalyticsAppTrendResponse.model_validate(payload)


@app.get("/api/analytics/insights/cost-value", response_model=CostValueMapResponse)
async def analytics_insight_cost_value(
    project_id: int | None = Query(default=None, ge=1),
    days: int = Query(default=ANALYTICS_DEFAULT_DAYS, ge=1, le=3650),
    session: AsyncSession = Depends(_session_with_rls_context),
) -> CostValueMapResponse:
    try:
        payload = await load_cost_value_map(session, project_id=project_id, days=days)
    except Exception as exc:
        logger.exception("analytics cost-value query failed")
        raise HTTPException(
            status_code=500,
            detail=_analytics_error_detail(
                "analytics_cost_value_query_failed",
                "Cost-vs-Value Daten konnten nicht geladen werden.",
            ),
        ) from exc
    return CostValueMapResponse.model_validate(payload)


@app.get("/api/analytics/insights/bloat", response_model=BloatExplorerResponse)
async def analytics_insight_bloat(
    project_id: int | None = Query(default=None, ge=1),
    days: int = Query(default=ANALYTICS_DEFAULT_DAYS, ge=1, le=3650),
    limit: int = Query(default=25, ge=1, le=200),
    session: AsyncSession = Depends(_session_with_rls_context),
) -> BloatExplorerResponse:
    try:
        payload = await load_bloat_explorer(
            session,
            project_id=project_id,
            days=days,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("analytics bloat query failed")
        raise HTTPException(
            status_code=500,
            detail=_analytics_error_detail(
                "analytics_bloat_query_failed",
                "Bloat-Explorer Daten konnten nicht geladen werden.",
            ),
        ) from exc
    return BloatExplorerResponse.model_validate(payload)


@app.get("/api/analytics/insights/data-model-pack", response_model=DataModelPackResponse)
async def analytics_insight_data_model_pack(
    project_id: int | None = Query(default=None, ge=1),
    metric: DataModelPackMetric = Query(default="static_byte_size_latest"),
    session: AsyncSession = Depends(_session_with_rls_context),
) -> DataModelPackResponse:
    try:
        payload = await load_data_model_pack(
            session,
            project_id=project_id,
            metric=metric,
        )
    except Exception as exc:
        logger.exception("analytics data-model-pack query failed")
        raise HTTPException(
            status_code=500,
            detail=_analytics_error_detail(
                "analytics_data_model_pack_query_failed",
                "Data-Model-Pack Daten konnten nicht geladen werden.",
            ),
        ) from exc
    return DataModelPackResponse.model_validate(payload)


@app.get("/api/analytics/insights/lineage-criticality", response_model=LineageCriticalityResponse)
async def analytics_insight_lineage_criticality(
    project_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=30, ge=1, le=200),
    session: AsyncSession = Depends(_session_with_rls_context),
) -> LineageCriticalityResponse:
    try:
        payload = await load_lineage_criticality(
            session,
            project_id=project_id,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("analytics lineage-criticality query failed")
        raise HTTPException(
            status_code=500,
            detail=_analytics_error_detail(
                "analytics_lineage_criticality_query_failed",
                "Lineage-Kritikalitaet konnte nicht geladen werden.",
            ),
        ) from exc
    return LineageCriticalityResponse.model_validate(payload)


@app.get("/api/analytics/insights/governance-ops", response_model=GovernanceOperationsResponse)
async def analytics_insight_governance_ops(
    project_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=ANALYTICS_DEFAULT_GOVERNANCE_LIMIT, ge=1, le=200),
    session: AsyncSession = Depends(_session_with_rls_context),
) -> GovernanceOperationsResponse:
    try:
        payload = await load_governance_operations(
            session,
            project_id=project_id,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("analytics governance-ops query failed")
        raise HTTPException(
            status_code=500,
            detail=_analytics_error_detail(
                "analytics_governance_ops_query_failed",
                "Governance-Operations Daten konnten nicht geladen werden.",
            ),
        ) from exc
    return GovernanceOperationsResponse.model_validate(payload)


@app.get("/api/graph/app/{app_id:path}", response_model=GraphResponse)
async def graph_for_app(app_id: str, depth: int = 1, session: AsyncSession = Depends(_session_with_rls_context)) -> GraphResponse:
    try:
        return await load_app_subgraph(session, app_id, depth=depth)
    except KeyError:
        raise HTTPException(status_code=404, detail="app not found")


@app.get("/api/graph/all")
async def graph_all(
    page_size: int | None = Query(default=None, ge=10, le=5000),
    after: str | None = Query(default=None),
    session: AsyncSession = Depends(_session_with_rls_context),
) -> GraphResponse | PaginatedGraphResponse:
    """Legacy alias kept for compatibility; now DB-backed to avoid stale local artifact results."""
    if page_size is not None:
        return await load_graph_response_paginated(
            session, page_size=page_size, after=after,
        )
    return await _load_graph_from_db(session)


@app.get("/api/graph/db")
async def graph_from_db(
    page_size: int | None = Query(default=None, ge=10, le=5000),
    after: str | None = Query(default=None),
    session: AsyncSession = Depends(_session_with_rls_context),
) -> GraphResponse | PaginatedGraphResponse:
    """Read all lineage graph data from PostgreSQL JSONB tables (all projects)."""
    if page_size is not None:
        return await load_graph_response_paginated(
            session, page_size=page_size, after=after,
        )
    return await _load_graph_from_db(session)


@app.get("/api/graph/project/{project_id}")
async def graph_for_project(
    project_id: int,
    page_size: int | None = Query(default=None, ge=10, le=5000),
    after: str | None = Query(default=None),
    session: AsyncSession = Depends(_session_with_rls_context),
) -> GraphResponse | PaginatedGraphResponse:
    """Read lineage graph data for a specific project. Supports cursor-based pagination."""
    if page_size is not None:
        return await load_graph_response_paginated(
            session, project_id=project_id, page_size=page_size, after=after,
        )
    return await _load_graph_from_db(session, project_id=project_id)


@app.get("/api/graph/node/{node_id:path}", response_model=GraphResponse)
async def graph_for_node(
    node_id: str,
    direction: str = "both",
    depth: int = 1,
    session: AsyncSession = Depends(_session_with_rls_context),
) -> GraphResponse:
    if direction not in {"up", "down", "both"}:
        raise HTTPException(status_code=400, detail="invalid direction")
    result = await load_node_subgraph(session, node_id, direction=direction, depth=depth)
    if not result.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return result


@app.get("/api/reports/orphans", response_model=OrphansReport)
async def orphans(session: AsyncSession = Depends(_session_with_rls_context)) -> OrphansReport:
    return await load_orphans_report(session)


@app.get("/api/app/{app_id:path}/usage")
async def app_usage(app_id: str, session: AsyncSession = Depends(_session_with_rls_context)):
    try:
        return await load_app_usage_payload(session, app_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="usage not found")
    except Exception:
        logger.exception("app usage query failed for %s", app_id)
        raise HTTPException(status_code=500, detail="usage query failed")


@app.get("/api/app/{app_id:path}/script")
async def app_script(app_id: str, session: AsyncSession = Depends(_session_with_rls_context)):
    try:
        return await load_app_script_payload(session, app_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="script not found")
    except Exception:
        logger.exception("app script query failed for %s", app_id)
        raise HTTPException(status_code=500, detail="script query failed")


@app.get("/api/fetch/status")
async def fetch_status(
    session: AsyncSession = Depends(_admin_session_with_rls_context),
):
    from app.models import Customer
    count_result = await session.execute(select(sa_func.count()).select_from(Customer))
    customer_count = count_result.scalar() or 0
    running_job_id = None
    async with fetch_jobs_lock:
        for job_id, job in fetch_jobs_registry.items():
            if job.get("status") in {"queued", "running"}:
                running_job_id = job_id
                break
    return {
        "canRun": customer_count > 0,
        "customersConfigured": customer_count,
        "tokenRequired": bool(settings.fetch_trigger_token),
        "runningJobId": running_job_id,
    }


@app.get("/api/fetch/jobs")
async def list_fetch_jobs(_admin: dict = Depends(require_admin)):
    async with fetch_jobs_lock:
        jobs = [_public_job(job) for job in fetch_jobs_registry.values()]
    jobs.sort(key=lambda item: item.get("updatedAt", ""), reverse=True)
    return {"jobs": jobs[:25]}


@app.get("/api/fetch/jobs/{job_id}")
async def get_fetch_job(job_id: str, _admin: dict = Depends(require_admin)):
    async with fetch_jobs_lock:
        job = fetch_jobs_registry.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="fetch job not found")
        return _public_job(job)


@app.get("/api/fetch/jobs/{job_id}/logs")
async def get_fetch_job_logs(job_id: str, _admin: dict = Depends(require_admin)):
    async with fetch_jobs_lock:
        job = fetch_jobs_registry.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="fetch job not found")
        return {
            "logs": list(job_logs.get(job_id, [])),
            "status": job.get("status"),
            "currentStep": job.get("currentStep"),
            "projectId": job.get("projectId"),
        }


@app.post("/api/fetch/jobs")
async def start_fetch_job(
    payload: FetchJobRequest,
    x_fetch_token: str | None = Header(default=None, alias="X-Fetch-Token"),
    admin_user: dict = Depends(require_admin),
):
    _assert_fetch_token(x_fetch_token)
    planned_steps = _normalize_steps(payload.steps)
    async with fetch_jobs_lock:
        for job in fetch_jobs_registry.values():
            if job.get("status") in {"queued", "running"}:
                raise HTTPException(status_code=409, detail="another fetch job is already running")

        job_id = uuid.uuid4().hex
        job_logs[job_id] = []
        job = {
            "jobId": job_id,
            "status": "queued",
            "projectId": payload.project_id,
            "requestedSteps": payload.steps if payload.steps else list(FETCH_STEP_ALL_ORDER),
            "plannedSteps": planned_steps,
            "completedSteps": [],
            "currentStep": None,
            "results": {},
            "error": None,
            "createdAt": _utc_now_iso(),
            "startedAt": _utc_now_iso(),
            "updatedAt": _utc_now_iso(),
            "finishedAt": None,
            "triggeredByUserId": int(admin_user["user_id"]),
        }
        fetch_jobs_registry[job_id] = job
        _prune_old_jobs()

    task = asyncio.create_task(
        _execute_fetch_job(
            job_id,
            payload,
            planned_steps,
            actor_user_id=int(admin_user["user_id"]),
            actor_role=str(admin_user.get("role", "admin")),
        )
    )
    async with fetch_jobs_lock:
        fetch_jobs_registry[job_id]["_task"] = task
        return _public_job(fetch_jobs_registry[job_id])


if is_prod() and settings.frontend_dist.exists():
    assets_dir = settings.frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_file = settings.frontend_dist / "index.html"

    @app.get("/")
    async def serve_root():
        return FileResponse(index_file)

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        candidate = settings.frontend_dist / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)
