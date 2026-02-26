from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert as pg_insert

from fetchers.fetch_apps import fetch_all_apps
from fetchers.fetch_data_connections import fetch_all_data_connections
from fetchers.fetch_lineage import fetch_app_edges_for_apps, fetch_lineage_for_apps
from fetchers.fetch_spaces import fetch_all_spaces
from fetchers.fetch_usage import fetch_usage_async
from fetchers.artifact_graph import build_snapshot_from_lineage_artifacts, build_snapshot_from_payloads
from shared.config import is_prod, settings
from shared.models import GraphResponse, HealthResponse, InventoryResponse, OrphansReport
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
    load_inventory,
    load_node_subgraph,
    load_orphans_report,
    load_spaces_payload,
)
from app.projects.routes import router as projects_router
from app.admin.routes import router as admin_router
from shared.qlik_client import QlikClient
from shared.security_headers import apply_security_headers
from shared.utils import ensure_dir, read_json, write_json


FetchStep = Literal["spaces", "apps", "data-connections", "lineage", "app-edges", "usage"]
FETCH_STEP_ORDER: list[FetchStep] = ["spaces", "apps", "data-connections", "lineage", "app-edges", "usage"]

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "output"
APPS_INVENTORY_FILE = OUTPUT_ROOT / "apps_inventory.json"
SPACES_FILE = OUTPUT_ROOT / "spaces.json"
LINEAGE_OUT_DIR = OUTPUT_ROOT / "lineage"
LINEAGE_SUCCESS_DIR = OUTPUT_ROOT / "lineage_success"
APP_EDGES_DIR = LINEAGE_SUCCESS_DIR
APP_USAGE_DIR = OUTPUT_ROOT / "appusage"
TENANT_DATA_CONNECTIONS_FILE = LINEAGE_OUT_DIR / "tenant_data_connections.json"


class FetchJobRequest(BaseModel):
    steps: list[FetchStep] | None = None
    limitApps: int | None = Field(default=None, ge=1)
    onlySpace: str | None = None
    clearOutputs: bool = False
    lineageConcurrency: int | None = Field(default=None, ge=1)
    usageConcurrency: int | None = Field(default=None, ge=1)
    usageWindowDays: int | None = Field(default=None, ge=1)
    project_id: int  # Credentials are loaded from the project's customer


app = FastAPI(title="Lineage Explorer API", docs_url=None, redoc_url=None)
app.include_router(auth_router, prefix="/api")
app.include_router(customers_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(admin_router, prefix="/api")

# CORS
origins = settings.dev_cors_origins or []
origins.append(settings.connect_src)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(set(origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


fetch_jobs_registry: dict[str, dict[str, Any]] = {}
fetch_jobs_lock = asyncio.Lock()
job_logs: dict[str, list[str]] = {}
MAX_FINISHED_JOBS = 50


def _write_local_fetch_artifacts_enabled() -> bool:
    raw = os.getenv("FETCH_WRITE_LOCAL_ARTIFACTS", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


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


def _log_time() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


async def _append_log(job_id: str, msg: str) -> None:
    async with fetch_jobs_lock:
        if job_id in job_logs:
            job_logs[job_id].append(f"[{_log_time()}] {msg}")


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def _assert_fetch_token(token: str | None) -> None:
    required = settings.fetch_trigger_token
    if required and token != required:
        raise HTTPException(status_code=403, detail="invalid fetch trigger token")


def _normalize_steps(steps: list[FetchStep] | None) -> list[FetchStep]:
    if not steps:
        return list(FETCH_STEP_ORDER)
    selected = set(steps)
    if "app-edges" in selected:
        selected.add("lineage")
    if "lineage" in selected or "usage" in selected:
        selected.add("apps")
    normalized = [step for step in FETCH_STEP_ORDER if step in selected]
    if not normalized:
        raise HTTPException(status_code=400, detail="no valid fetch steps supplied")
    return normalized


def _build_qlik_client() -> QlikClient:
    """Build a QlikClient from env vars (set by _load_project_creds_to_env before each job)."""
    tenant_url = os.getenv("QLIK_TENANT_URL", "").strip()
    api_key = os.getenv("QLIK_API_KEY", "").strip()
    if not tenant_url or not api_key:
        raise RuntimeError("Qlik credentials not loaded — ensure project has a customer with valid credentials")
    return QlikClient(
        base_url=tenant_url,
        api_key=api_key,
        timeout=float(os.getenv("QLIK_TIMEOUT", "30")),
        max_retries=int(os.getenv("QLIK_MAX_RETRIES", "5")),
    )


def _load_apps_inventory() -> list[dict[str, Any]]:
    if not APPS_INVENTORY_FILE.exists():
        raise RuntimeError("apps inventory missing; run apps step first")
    payload = read_json(APPS_INVENTORY_FILE)
    if isinstance(payload, dict) and isinstance(payload.get("apps"), list):
        return [item for item in payload["apps"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise RuntimeError("apps inventory is invalid")


def _is_http_ok(status: Any) -> bool:
    return isinstance(status, int) and 200 <= status < 300


def _extract_successful_lineage_app_ids() -> set[str]:
    app_ids: set[str] = set()
    if not LINEAGE_OUT_DIR.exists():
        return app_ids

    for path in LINEAGE_OUT_DIR.glob("*__lineage.json"):
        try:
            payload = read_json(path)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue

        endpoints = payload.get("endpoints")
        if not isinstance(endpoints, dict):
            continue
        source = endpoints.get("source") or {}
        overview = endpoints.get("overview") or {}
        if not isinstance(source, dict) or not isinstance(overview, dict):
            continue
        if not (_is_http_ok(source.get("status")) and _is_http_ok(overview.get("status"))):
            continue

        app = payload.get("app") or {}
        if not isinstance(app, dict):
            continue
        app_id = app.get("id")
        if app_id:
            app_ids.add(str(app_id))

    return app_ids


def _select_apps_for_app_edges(apps: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    eligible = [app for app in apps if bool(app.get("lineageSuccess"))]
    if eligible:
        return eligible, "lineage_step_runtime"

    successful_app_ids = _extract_successful_lineage_app_ids()
    if not successful_app_ids:
        return [], "no_successful_lineage_found"

    filtered: list[dict[str, Any]] = []
    for app in apps:
        app_id = app.get("appId")
        if app_id and str(app_id) in successful_app_ids:
            filtered.append(app)
    return filtered, "lineage_output_scan"


def _clear_app_edges_artifacts(directory: Path) -> int:
    if not directory.exists() or not directory.is_dir():
        return 0
    removed = 0
    for path in directory.glob("*.json"):
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
    return removed


def _clear_lineage_artifacts(directory: Path) -> int:
    if not directory.exists() or not directory.is_dir():
        return 0
    removed = 0
    for path in directory.glob("*__lineage.json"):
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
    return removed


def _clear_outputs_for_steps(steps: list[FetchStep]) -> dict[str, Any]:
    cleared: dict[str, Any] = {"files": [], "dirs": []}
    selected = set(steps)

    if "apps" in selected and APPS_INVENTORY_FILE.exists():
        APPS_INVENTORY_FILE.unlink()
        cleared["files"].append(str(APPS_INVENTORY_FILE))

    if "spaces" in selected and SPACES_FILE.exists():
        SPACES_FILE.unlink()
        cleared["files"].append(str(SPACES_FILE))

    if "data-connections" in selected and TENANT_DATA_CONNECTIONS_FILE.exists():
        TENANT_DATA_CONNECTIONS_FILE.unlink()
        cleared["files"].append(str(TENANT_DATA_CONNECTIONS_FILE))

    if "lineage" in selected:
        removed = _clear_lineage_artifacts(LINEAGE_OUT_DIR)
        if removed:
            cleared["files"].append(f"{LINEAGE_OUT_DIR}/*__lineage.json ({removed})")

    if "app-edges" in selected:
        removed = _clear_app_edges_artifacts(APP_EDGES_DIR)
        if removed:
            cleared["files"].append(f"{APP_EDGES_DIR}/*.json ({removed})")

    if "usage" in selected and APP_USAGE_DIR.exists():
        shutil.rmtree(APP_USAGE_DIR)
        cleared["dirs"].append(str(APP_USAGE_DIR))

    return cleared


async def _run_apps_step(request: FetchJobRequest) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = _build_qlik_client()
    try:
        apps = await fetch_all_apps(client, limit_apps=request.limitApps, only_space=request.onlySpace)
    finally:
        await client.close()

    wrote_local = False
    if _write_local_fetch_artifacts_enabled():
        ensure_dir(APPS_INVENTORY_FILE.parent)
        write_json(APPS_INVENTORY_FILE, {"count": len(apps), "apps": apps})
        wrote_local = True
    return apps, {"count": len(apps), "storage": "db-first-memory", "localArtifactWritten": wrote_local}


async def _run_spaces_step() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = _build_qlik_client()
    limit = int(os.getenv("FETCH_SPACES_LIMIT", "100"))
    try:
        spaces = await fetch_all_spaces(client, limit=limit)
    finally:
        await client.close()

    wrote_local = False
    if _write_local_fetch_artifacts_enabled():
        ensure_dir(SPACES_FILE.parent)
        write_json(SPACES_FILE, {"count": len(spaces), "spaces": spaces})
        wrote_local = True
    return spaces, {"count": len(spaces), "storage": "db-first-memory", "localArtifactWritten": wrote_local}


async def _run_data_connections_step() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = _build_qlik_client()
    limit = int(os.getenv("FETCH_DATA_CONNECTIONS_LIMIT", "100"))
    try:
        connections = await fetch_all_data_connections(client, limit=limit)
    finally:
        await client.close()

    wrote_local = False
    if _write_local_fetch_artifacts_enabled():
        ensure_dir(TENANT_DATA_CONNECTIONS_FILE.parent)
        write_json(TENANT_DATA_CONNECTIONS_FILE, {"count": len(connections), "data": connections})
        wrote_local = True
    return connections, {"count": len(connections), "storage": "db-first-memory", "localArtifactWritten": wrote_local}


async def _run_lineage_step(
    request: FetchJobRequest,
    apps: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    write_local = _write_local_fetch_artifacts_enabled()
    if write_local:
        ensure_dir(LINEAGE_OUT_DIR)

    lineage_concurrency = request.lineageConcurrency or int(os.getenv("QLIK_LINEAGE_CONCURRENCY", "5"))
    client = _build_qlik_client()
    lineage_payloads: list[dict[str, Any]] = []
    lineage_result = await fetch_lineage_for_apps(
        client=client,
        apps=apps,
        outdir=LINEAGE_OUT_DIR if write_local else None,
        success_outdir=None,
        concurrency=lineage_concurrency,
        collector=lineage_payloads,
    )
    return lineage_payloads, {
        "apps": len(apps),
        "lineage": lineage_result,
        "storage": "db-first-memory",
        "localArtifactWritten": write_local,
    }


async def _run_app_edges_step(
    request: FetchJobRequest,
    apps: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    write_local = _write_local_fetch_artifacts_enabled()
    if write_local:
        ensure_dir(APP_EDGES_DIR)
        _clear_app_edges_artifacts(APP_EDGES_DIR)
    eligible_apps, filter_source = _select_apps_for_app_edges(apps)
    if not eligible_apps:
        return [], {
            "apps": len(apps),
            "eligibleApps": 0,
            "filterSource": filter_source,
            "appEdges": {"success": 0, "failed": 0, "edges": 0},
            "storage": "db-first-memory",
            "localArtifactWritten": False,
        }

    lineage_concurrency = request.lineageConcurrency or int(os.getenv("QLIK_LINEAGE_CONCURRENCY", "5"))
    client = _build_qlik_client()
    app_edges_payloads: list[dict[str, Any]] = []
    edges_result = await fetch_app_edges_for_apps(
        client=client,
        apps=eligible_apps,
        outdir=APP_EDGES_DIR if write_local else None,
        success_outdir=None,
        concurrency=lineage_concurrency,
        up_depth=os.getenv("QLIK_APP_EDGES_UP_DEPTH", "-1"),
        collapse=os.getenv("QLIK_APP_EDGES_COLLAPSE", "true"),
        collector=app_edges_payloads,
    )
    return app_edges_payloads, {
        "apps": len(apps),
        "eligibleApps": len(eligible_apps),
        "filterSource": filter_source,
        "appEdges": {
            "success": edges_result.get("success", 0),
            "failed": edges_result.get("failed", 0),
            "edges": len(edges_result.get("edges", [])),
        },
        "storage": "db-first-memory",
        "localArtifactWritten": write_local,
    }


async def _run_usage_step(
    request: FetchJobRequest,
    apps: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    write_local = _write_local_fetch_artifacts_enabled()
    if write_local:
        ensure_dir(APP_USAGE_DIR)
    client = _build_qlik_client()
    usage_payloads: list[dict[str, Any]] = []
    await fetch_usage_async(
        apps=apps,
        client=client,
        window_days=request.usageWindowDays,
        outdir=APP_USAGE_DIR if write_local else None,
        concurrency=request.usageConcurrency,
        close_client=True,
        collector=usage_payloads,
    )
    return usage_payloads, {"apps": len(apps), "storage": "db-first-memory", "localArtifactWritten": write_local}


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
    usage_payloads: list[dict[str, Any]] = []
    app_edges_payloads: list[dict[str, Any]] = []
    step_labels: dict[str, str] = {
        "spaces": "Spaces laden",
        "apps": "Apps laden",
        "data-connections": "Datenverbindungen laden",
        "lineage": "Lineage berechnen",
        "app-edges": "App-Kanten berechnen",
        "usage": "Usage-Daten laden",
    }
    try:
        await _update_job(job_id, status="running")
        await _append_log(job_id, f"Job gestartet · {len(steps)} Schritt(e) geplant")

        await _append_log(job_id, f"Lade Credentials für Projekt {project_id}…")
        await _load_project_creds_to_env(project_id, actor_user_id=actor_user_id, actor_role=actor_role)
        await _append_log(job_id, "✓ Credentials geladen")

        if _write_local_fetch_artifacts_enabled():
            cleared = _clear_outputs_for_steps(steps)
            if cleared.get("files") or cleared.get("dirs"):
                await _append_log(job_id, "Alte Ausgabedateien bereinigt")
        else:
            cleared = {"files": [], "dirs": [], "skipped": True, "reason": "local artifacts disabled (DB-first mode)"}
            await _append_log(job_id, "Lokale Fetch-Artefakte deaktiviert (DB-first Mode)")
        await _update_job(job_id, cleanup=cleared)

        for i, step in enumerate(steps, 1):
            label = step_labels.get(step, step)
            await _append_log(job_id, f"Schritt {i}/{len(steps)}: {label}…")
            await _update_job(job_id, currentStep=step)

            if step == "spaces":
                spaces_cache, result = await _run_spaces_step()
                await _append_log(job_id, f"✓ {result.get('count', 0)} Spaces geladen")
            elif step == "apps":
                apps_cache, result = await _run_apps_step(request)
                await _append_log(job_id, f"✓ {result.get('count', 0)} Apps geladen")
            elif step == "data-connections":
                data_connections_cache, result = await _run_data_connections_step()
                await _append_log(job_id, f"✓ {result.get('count', 0)} Datenverbindungen geladen")
            elif step == "lineage":
                if apps_cache is None:
                    if _write_local_fetch_artifacts_enabled():
                        apps_cache = _load_apps_inventory()
                    else:
                        raise RuntimeError("apps step data missing in DB-first mode; include 'apps' before 'lineage'")
                _lineage_payloads, result = await _run_lineage_step(request, apps_cache)
                await _append_log(job_id, f"✓ Lineage für {len(apps_cache)} Apps berechnet")
            elif step == "app-edges":
                if apps_cache is None:
                    if _write_local_fetch_artifacts_enabled():
                        apps_cache = _load_apps_inventory()
                    else:
                        raise RuntimeError("apps step data missing in DB-first mode; include 'apps' before 'app-edges'")
                app_edges_payloads, result = await _run_app_edges_step(request, apps_cache)
                edges = result.get("appEdges", {}).get("edges", 0)
                await _append_log(job_id, f"✓ {edges} App-Kanten gefunden")
            elif step == "usage":
                if apps_cache is None:
                    if _write_local_fetch_artifacts_enabled():
                        apps_cache = _load_apps_inventory()
                    else:
                        raise RuntimeError("apps step data missing in DB-first mode; include 'apps' before 'usage'")
                usage_payloads, result = await _run_usage_step(request, apps_cache)
                await _append_log(job_id, f"✓ Usage-Daten geladen")
            else:
                continue
            await _complete_job_step(job_id, step, result)

        await _append_log(job_id, "Speichere Daten in Datenbank…")
        db_result = await _run_db_store_step(
            project_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            apps_data=apps_cache,
            spaces_data=spaces_cache,
            data_connections_data=data_connections_cache,
            usage_payloads=usage_payloads,
            app_edges_payloads=app_edges_payloads,
        )
        await _append_log(
            job_id,
            f"✓ Gespeichert: {db_result.get('apps', 0)} Apps · "
            f"{db_result.get('nodes', 0)} Knoten · {db_result.get('edges', 0)} Kanten"
        )
        await _append_log(job_id, "✓ Job erfolgreich abgeschlossen")
        await _update_job(job_id, status="completed", finishedAt=_utc_now_iso(), currentStep=None, dbStore=db_result)
    except Exception as exc:
        await _append_log(job_id, f"✗ Fehler: {exc}")
        await _update_job(
            job_id,
            status="failed",
            error=str(exc),
            finishedAt=_utc_now_iso(),
            currentStep=None,
        )


async def _load_project_creds_to_env(project_id: int, *, actor_user_id: int, actor_role: str) -> None:
    """Load credentials from a project's customer into os.environ for the duration of a fetch."""
    from app.database import AsyncSessionLocal
    from app.models import Customer, Project
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
        os.environ["QLIK_TENANT_URL"] = customer.tenant_url
        os.environ["QLIK_API_KEY"] = customer.api_key
        print(f"Loaded credentials for project {project_id} from customer '{customer.name}'")


def _iter_usage_artifacts(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists() or not directory.is_dir():
        return []
    payloads: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = read_json(path)
        except Exception:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _infer_app_id_from_script_artifact(path: Path, payload: dict[str, Any] | None = None) -> str | None:
    payload = payload or {}
    candidate = payload.get("appId")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    stem = path.stem
    if "__" in stem:
        last = stem.split("__")[-1].strip()
        if last:
            return last
    return stem.strip() or None


def _iter_script_artifacts(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists() or not directory.is_dir():
        return []
    artifacts: list[dict[str, Any]] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".json", ".qvs", ".txt"}:
            continue
        payload: dict[str, Any]
        script_text: str | None = None
        source = suffix.lstrip(".")

        if suffix == ".json":
            try:
                raw = read_json(path)
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            payload = dict(raw)
            candidate_script = (
                payload.get("script")
                or payload.get("loadScript")
                or payload.get("load_script")
                or payload.get("text")
            )
            if not isinstance(candidate_script, str):
                continue
            script_text = candidate_script
            source = str(payload.get("source") or source)
        else:
            try:
                script_text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            payload = {
                "script": script_text,
                "source": source,
                "fileName": path.name,
            }

        app_id = _infer_app_id_from_script_artifact(path, payload)
        if not app_id or script_text is None:
            continue
        payload.setdefault("appId", app_id)
        payload.setdefault("fileName", path.name)
        payload.setdefault("source", source)
        artifacts.append(
            {
                "appId": app_id,
                "script": script_text,
                "source": str(payload.get("source") or source),
                "fileName": str(payload.get("fileName") or path.name),
                "data": payload,
            }
        )
    return artifacts


def _space_payload_columns(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "space_type": None,
            "owner_id": None,
            "space_id_payload": None,
            "tenant_id": None,
            "created_at_source": None,
            "space_name": None,
            "updated_at_source": None,
        }
    return {
        "space_type": item.get("type"),
        "owner_id": item.get("ownerId") or item.get("ownerID"),
        "space_id_payload": item.get("spaceId") or item.get("spaceID") or item.get("id"),
        "tenant_id": item.get("tenantId") or item.get("tenantID"),
        "created_at_source": item.get("createdAt"),
        "space_name": item.get("spaceName") or item.get("spacename") or item.get("name"),
        "updated_at_source": item.get("updatedAt"),
    }


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _datetime_or_none(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _app_payload_columns(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "name_value": None,
            "app_id_payload": None,
            "status": None,
            "app_name": None,
            "space_id_payload": None,
            "file_name": None,
            "item_type": None,
            "edges_count": None,
            "nodes_count": None,
            "root_node_id": None,
            "lineage_fetched": None,
            "lineage_success": None,
            "fetched_at": None,
        }
    return {
        "name_value": _str_or_none(item.get("name")),
        "app_id_payload": _str_or_none(item.get("appId") or item.get("id")),
        "status": _int_or_none(item.get("status")),
        "app_name": _str_or_none(item.get("appName") or item.get("name")),
        "space_id_payload": _str_or_none(item.get("spaceId")),
        "file_name": _str_or_none(item.get("fileName")),
        "item_type": _str_or_none(item.get("itemType")),
        "edges_count": _int_or_none(item.get("edgesCount")),
        "nodes_count": _int_or_none(item.get("nodesCount")),
        "root_node_id": _str_or_none(item.get("rootNodeId")),
        "lineage_fetched": _bool_or_none(item.get("lineageFetched")),
        "lineage_success": _bool_or_none(item.get("lineageSuccess")),
        "fetched_at": _datetime_or_none(item.get("fetched_at")) or datetime.now(timezone.utc),
    }


def _usage_payload_columns(item: dict[str, Any]) -> dict[str, Any]:
    usage = item.get("usage") if isinstance(item.get("usage"), dict) else {}
    generated_at_text = _str_or_none(item.get("generatedAt"))
    return {
        "app_id_payload": _str_or_none(item.get("appId")),
        "app_name": _str_or_none(item.get("appName")),
        "window_days": _int_or_none(item.get("windowDays")),
        "usage_reloads": _int_or_none(usage.get("reloads")),
        "usage_app_opens": _int_or_none(usage.get("appOpens")),
        "usage_sheet_views": _int_or_none(usage.get("sheetViews")),
        "usage_unique_users": _int_or_none(usage.get("uniqueUsers")),
        "usage_last_reload_at": _str_or_none(usage.get("lastReloadAt")),
        "usage_last_viewed_at": _str_or_none(usage.get("lastViewedAt")),
        "usage_classification": _str_or_none(usage.get("classification")),
        "connections": item.get("connections") if isinstance(item.get("connections"), list) else [],
        "generated_at_payload": generated_at_text,
        "artifact_file_name": _str_or_none(item.get("_artifactFileName")),
        "generated_at": _datetime_or_none(generated_at_text) or datetime.now(timezone.utc),
    }


async def _run_db_store_step(
    project_id: int,
    *,
    actor_user_id: int,
    actor_role: str,
    apps_data: list[dict[str, Any]] | None = None,
    spaces_data: list[dict[str, Any]] | None = None,
    data_connections_data: list[dict[str, Any]] | None = None,
    usage_payloads: list[dict[str, Any]] | None = None,
    app_edges_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Persist fetch outputs into PostgreSQL (DB-first; artifact fallback when needed)."""
    from app.database import AsyncSessionLocal
    from app.models import (
        LineageEdge,
        LineageNode,
        QlikApp,
        QlikAppScript,
        QlikAppUsage,
        QlikDataConnection,
        QlikSpace,
    )

    stored: dict[str, int] = {
        "apps": 0,
        "nodes": 0,
        "edges": 0,
        "spaces": 0,
        "dataConnections": 0,
        "usage": 0,
        "scripts": 0,
        "skippedLineageFiles": 0,
    }

    if app_edges_payloads is not None:
        snapshot, skipped_lineage_files = build_snapshot_from_payloads(app_edges_payloads)
    elif _write_local_fetch_artifacts_enabled():
        snapshot, skipped_lineage_files = build_snapshot_from_lineage_artifacts(APP_EDGES_DIR)
    else:
        snapshot, skipped_lineage_files = build_snapshot_from_payloads([])
    stored["skippedLineageFiles"] = len(skipped_lineage_files)

    apps_inventory_by_id: dict[str, dict[str, Any]] = {}
    app_lookup_for_nodes: dict[str, dict[str, Any]] = {}
    if apps_data is not None:
        apps_list = apps_data
    elif _write_local_fetch_artifacts_enabled() and APPS_INVENTORY_FILE.exists():
        payload = read_json(APPS_INVENTORY_FILE)
        apps_list = payload.get("apps", payload) if isinstance(payload, dict) else payload
    else:
        apps_list = []
    if apps_list is not None:
        for app_data in (apps_list if isinstance(apps_list, list) else []):
            if not isinstance(app_data, dict):
                continue
            app_id = app_data.get("appId")
            if not app_id:
                continue
            apps_inventory_by_id[str(app_id)] = dict(app_data)

    try:
        async with AsyncSessionLocal() as session:
            await apply_rls_context(session, actor_user_id, actor_role)
            # --- apps (merge inventory + lineage-derived metadata for UI transformations) ---
            all_app_ids = set(apps_inventory_by_id) | set(snapshot.apps)
            for app_id in sorted(all_app_ids):
                inventory_payload = dict(apps_inventory_by_id.get(app_id) or {})
                lineage_app = dict(snapshot.apps.get(app_id) or {})
                merged_data: dict[str, Any] = {}
                merged_data.update(inventory_payload)
                merged_data.update(lineage_app)
                merged_data.setdefault("appId", app_id)
                if "appName" not in merged_data and inventory_payload.get("name"):
                    merged_data["appName"] = inventory_payload.get("name")
                if "name" not in merged_data and merged_data.get("appName"):
                    merged_data["name"] = merged_data.get("appName")
                app_lookup_for_nodes[app_id] = {
                    "appName": merged_data.get("appName") or merged_data.get("name") or app_id,
                    "spaceId": merged_data.get("spaceId"),
                }
                app_cols = _app_payload_columns(merged_data)

                stmt = pg_insert(QlikApp).values(
                    project_id=project_id,
                    app_id=app_id,
                    space_id=merged_data.get("spaceId"),
                    **app_cols,
                    data=merged_data,
                ).on_conflict_do_update(
                    index_elements=["project_id", "app_id"],
                    set_={**app_cols, "data": merged_data, "space_id": merged_data.get("spaceId")},
                )
                await session.execute(stmt)
                stored["apps"] += 1

            # --- spaces ---
            if spaces_data is not None:
                spaces_list = spaces_data
            elif _write_local_fetch_artifacts_enabled() and SPACES_FILE.exists():
                spaces_payload = read_json(SPACES_FILE)
                spaces_list = spaces_payload.get("spaces", []) if isinstance(spaces_payload, dict) else []
            else:
                spaces_list = []
            if spaces_list:
                space_name_by_id: dict[str, str] = {}
                for item in spaces_list if isinstance(spaces_list, list) else []:
                    if not isinstance(item, dict):
                        continue
                    space_id = item.get("spaceId") or item.get("id")
                    if not space_id:
                        continue
                    space_name = item.get("spaceName") or item.get("spacename") or item.get("name")
                    if isinstance(space_name, str) and space_name.strip():
                        space_name_by_id[str(space_id)] = space_name.strip()
                    space_cols = _space_payload_columns(item)
                    stmt = pg_insert(QlikSpace).values(
                        project_id=project_id,
                        space_id=str(space_id),
                        **space_cols,
                        data=item,
                    ).on_conflict_do_update(
                        index_elements=["project_id", "space_id"],
                        set_={**space_cols, "data": item},
                    )
                    await session.execute(stmt)
                    stored["spaces"] += 1
            else:
                space_name_by_id = {}

            # --- data connections ---
            if data_connections_data is not None:
                connections = data_connections_data
            elif _write_local_fetch_artifacts_enabled() and TENANT_DATA_CONNECTIONS_FILE.exists():
                connections_payload = read_json(TENANT_DATA_CONNECTIONS_FILE)
                connections = connections_payload.get("data", []) if isinstance(connections_payload, dict) else []
            else:
                connections = []
            if connections:
                for item in connections if isinstance(connections, list) else []:
                    if not isinstance(item, dict):
                        continue
                    connection_id = item.get("id") or item.get("qID") or item.get("qEngineObjectID")
                    if not connection_id:
                        continue
                    stmt = pg_insert(QlikDataConnection).values(
                        project_id=project_id,
                        connection_id=str(connection_id),
                        space_id=item.get("space"),
                        data=item,
                    ).on_conflict_do_update(
                        index_elements=["project_id", "connection_id"],
                        set_={"data": item, "space_id": item.get("space")},
                    )
                    await session.execute(stmt)
                    stored["dataConnections"] += 1

            # --- usage ---
            if usage_payloads is not None:
                usage_records = usage_payloads
            elif _write_local_fetch_artifacts_enabled():
                usage_records = _iter_usage_artifacts(APP_USAGE_DIR)
            else:
                usage_records = []
            for usage_payload in usage_records:
                app_id = usage_payload.get("appId")
                if not app_id:
                    continue
                usage_cols = _usage_payload_columns(usage_payload if isinstance(usage_payload, dict) else {})
                stmt = pg_insert(QlikAppUsage).values(
                    project_id=project_id,
                    app_id=str(app_id),
                    **usage_cols,
                    data=usage_payload,
                ).on_conflict_do_update(
                    index_elements=["project_id", "app_id"],
                    set_={**usage_cols, "data": usage_payload},
                )
                await session.execute(stmt)
                stored["usage"] += 1

            # --- scripts (optional local source for now; DB becomes runtime source) ---
            script_artifacts = _iter_script_artifacts(settings.scripts_dir) if _write_local_fetch_artifacts_enabled() else []
            for script_artifact in script_artifacts:
                stmt = pg_insert(QlikAppScript).values(
                    project_id=project_id,
                    app_id=str(script_artifact["appId"]),
                    script=str(script_artifact["script"]),
                    source=script_artifact.get("source"),
                    file_name=script_artifact.get("fileName"),
                    data=script_artifact["data"],
                ).on_conflict_do_update(
                    index_elements=["project_id", "app_id"],
                    set_={
                        "script": str(script_artifact["script"]),
                        "source": script_artifact.get("source"),
                        "file_name": script_artifact.get("fileName"),
                        "data": script_artifact["data"],
                    },
                )
                await session.execute(stmt)
                stored["scripts"] += 1

            # --- nodes ---
            for node_id, node in snapshot.nodes.items():
                node_payload = dict(node)
                node_meta = dict(node_payload.get("meta") or {})
                node_app_id = (
                    node_payload.get("group")
                    or node_meta.get("appId")
                    or node_meta.get("app_id")
                    or ((node_meta.get("id") if node_payload.get("type") == "app" else None))
                )
                if node_app_id:
                    app_info = app_lookup_for_nodes.get(str(node_app_id))
                    node_meta.setdefault("appId", str(node_app_id))
                    if app_info:
                        app_name_val = app_info.get("appName")
                        space_id_val = app_info.get("spaceId")
                        if app_name_val:
                            node_meta.setdefault("appName", str(app_name_val))
                        if space_id_val:
                            node_meta.setdefault("spaceId", str(space_id_val))
                            space_name_val = space_name_by_id.get(str(space_id_val))
                            if space_name_val:
                                node_meta.setdefault("spaceName", str(space_name_val))
                if node_meta:
                    node_payload["meta"] = node_meta
                stmt = pg_insert(LineageNode).values(
                    project_id=project_id,
                    node_id=node_id,
                    app_id=(node_meta or {}).get("id") if node_payload.get("type") == "app" else None,
                    node_type=node_payload.get("type"),
                    data=node_payload,
                ).on_conflict_do_update(
                    index_elements=["project_id", "node_id"],
                    set_={
                        "data": node_payload,
                        "node_type": node_payload.get("type"),
                        "app_id": (node_meta or {}).get("id") if node_payload.get("type") == "app" else None,
                    },
                )
                await session.execute(stmt)
                stored["nodes"] += 1

            # --- edges ---
            for edge_id, edge in snapshot.edges.items():
                edge_context = edge.get("context") or {}
                stmt = pg_insert(LineageEdge).values(
                    project_id=project_id,
                    edge_id=edge_id,
                    app_id=edge_context.get("appId"),
                    source_node_id=edge.get("source"),
                    target_node_id=edge.get("target"),
                    data=dict(edge),
                ).on_conflict_do_update(
                    index_elements=["project_id", "edge_id"],
                    set_={
                        "data": dict(edge),
                        "app_id": edge_context.get("appId"),
                        "source_node_id": edge.get("source"),
                        "target_node_id": edge.get("target"),
                    },
                )
                await session.execute(stmt)
                stored["edges"] += 1

            await session.commit()
    except Exception as exc:
        print(f"Warning: DB store step failed: {exc}")
    return stored


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
async def dashboard_stats(session: AsyncSession = Depends(_session_with_rls_context)) -> HealthResponse:
    """Authenticated dashboard stats with DB-backed app/node/edge counts (RLS-scoped)."""
    from app.models import QlikApp, LineageNode, LineageEdge

    apps_result = await session.execute(select(sa_func.count()).select_from(QlikApp))
    nodes_result = await session.execute(select(sa_func.count()).select_from(LineageNode))
    edges_result = await session.execute(select(sa_func.count()).select_from(LineageEdge))
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
        raise HTTPException(status_code=500, detail="data connections query failed")


@app.get("/api/spaces")
async def spaces(session: AsyncSession = Depends(_session_with_rls_context)):
    return await load_spaces_payload(session)


@app.get("/api/graph/app/{app_id:path}", response_model=GraphResponse)
async def graph_for_app(app_id: str, depth: int = 1, session: AsyncSession = Depends(_session_with_rls_context)) -> GraphResponse:
    try:
        return await load_app_subgraph(session, app_id, depth=depth)
    except KeyError:
        raise HTTPException(status_code=404, detail="app not found")


@app.get("/api/graph/all", response_model=GraphResponse)
async def graph_all(session: AsyncSession = Depends(_session_with_rls_context)) -> GraphResponse:
    """Legacy alias kept for compatibility; now DB-backed to avoid stale local artifact results."""
    return await _load_graph_from_db(session)


@app.get("/api/graph/db", response_model=GraphResponse)
async def graph_from_db(session: AsyncSession = Depends(_session_with_rls_context)) -> GraphResponse:
    """Read all lineage graph data from PostgreSQL JSONB tables (all projects)."""
    return await _load_graph_from_db(session)


@app.get("/api/graph/project/{project_id}", response_model=GraphResponse)
async def graph_for_project(project_id: int, session: AsyncSession = Depends(_session_with_rls_context)) -> GraphResponse:
    """Read lineage graph data for a specific project from PostgreSQL."""
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
        raise HTTPException(status_code=500, detail="usage query failed")


@app.get("/api/app/{app_id:path}/script")
async def app_script(app_id: str, session: AsyncSession = Depends(_session_with_rls_context)):
    try:
        return await load_app_script_payload(session, app_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="script not found")
    except Exception:
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
            "requestedSteps": payload.steps if payload.steps else list(FETCH_STEP_ORDER),
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
