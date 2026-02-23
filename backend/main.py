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
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from fetchers.fetch_apps import fetch_all_apps
from fetchers.fetch_data_connections import fetch_all_data_connections
from fetchers.fetch_lineage import fetch_app_edges_for_apps, fetch_lineage_for_apps
from fetchers.fetch_spaces import fetch_all_spaces
from fetchers.fetch_usage import fetch_usage_async
from fetchers.graph_store import GraphStore
from shared.config import is_prod, settings
from shared.models import GraphResponse, HealthResponse, InventoryResponse, OrphansReport
from app.auth.routes import router as auth_router
from app.customers.routes import router as customers_router
from app.auth.utils import get_current_user_id
from app.database import get_session
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


store = GraphStore(
    settings.data_dir,
    settings.spaces_file or SPACES_FILE,
    usage_dir=settings.usage_dir,
    scripts_dir=settings.scripts_dir,
    data_connections_file=settings.data_connections_file,
)
fetch_jobs_registry: dict[str, dict[str, Any]] = {}
fetch_jobs_lock = asyncio.Lock()
job_logs: dict[str, list[str]] = {}
MAX_FINISHED_JOBS = 50


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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

    ensure_dir(APPS_INVENTORY_FILE.parent)
    write_json(APPS_INVENTORY_FILE, {"count": len(apps), "apps": apps})
    return apps, {"count": len(apps), "output": str(APPS_INVENTORY_FILE)}


async def _run_spaces_step() -> dict[str, Any]:
    client = _build_qlik_client()
    limit = int(os.getenv("FETCH_SPACES_LIMIT", "100"))
    try:
        spaces = await fetch_all_spaces(client, limit=limit)
    finally:
        await client.close()

    ensure_dir(SPACES_FILE.parent)
    write_json(SPACES_FILE, {"count": len(spaces), "spaces": spaces})
    return {"count": len(spaces), "output": str(SPACES_FILE)}


async def _run_data_connections_step() -> dict[str, Any]:
    client = _build_qlik_client()
    limit = int(os.getenv("FETCH_DATA_CONNECTIONS_LIMIT", "100"))
    try:
        connections = await fetch_all_data_connections(client, limit=limit)
    finally:
        await client.close()

    ensure_dir(TENANT_DATA_CONNECTIONS_FILE.parent)
    write_json(TENANT_DATA_CONNECTIONS_FILE, {"count": len(connections), "data": connections})
    return {"count": len(connections), "output": str(TENANT_DATA_CONNECTIONS_FILE)}


async def _run_lineage_step(request: FetchJobRequest, apps: list[dict[str, Any]]) -> dict[str, Any]:
    ensure_dir(LINEAGE_OUT_DIR)

    lineage_concurrency = request.lineageConcurrency or int(os.getenv("QLIK_LINEAGE_CONCURRENCY", "5"))
    client = _build_qlik_client()
    lineage_result = await fetch_lineage_for_apps(
        client=client,
        apps=apps,
        outdir=LINEAGE_OUT_DIR,
        success_outdir=None,
        concurrency=lineage_concurrency,
    )
    return {
        "apps": len(apps),
        "lineage": lineage_result,
        "output": str(LINEAGE_OUT_DIR),
    }


async def _run_app_edges_step(request: FetchJobRequest, apps: list[dict[str, Any]]) -> dict[str, Any]:
    ensure_dir(APP_EDGES_DIR)
    _clear_app_edges_artifacts(APP_EDGES_DIR)
    eligible_apps, filter_source = _select_apps_for_app_edges(apps)
    if not eligible_apps:
        return {
            "apps": len(apps),
            "eligibleApps": 0,
            "filterSource": filter_source,
            "appEdges": {"success": 0, "failed": 0, "edges": 0},
            "output": str(APP_EDGES_DIR),
        }

    lineage_concurrency = request.lineageConcurrency or int(os.getenv("QLIK_LINEAGE_CONCURRENCY", "5"))
    client = _build_qlik_client()
    edges_result = await fetch_app_edges_for_apps(
        client=client,
        apps=eligible_apps,
        outdir=APP_EDGES_DIR,
        success_outdir=None,
        concurrency=lineage_concurrency,
        up_depth=os.getenv("QLIK_APP_EDGES_UP_DEPTH", "-1"),
        collapse=os.getenv("QLIK_APP_EDGES_COLLAPSE", "true"),
    )
    return {
        "apps": len(apps),
        "eligibleApps": len(eligible_apps),
        "filterSource": filter_source,
        "appEdges": {
            "success": edges_result.get("success", 0),
            "failed": edges_result.get("failed", 0),
            "edges": len(edges_result.get("edges", [])),
        },
        "output": str(APP_EDGES_DIR),
    }


async def _run_usage_step(request: FetchJobRequest, apps: list[dict[str, Any]]) -> dict[str, Any]:
    ensure_dir(APP_USAGE_DIR)
    client = _build_qlik_client()
    await fetch_usage_async(
        apps=apps,
        client=client,
        window_days=request.usageWindowDays,
        outdir=APP_USAGE_DIR,
        concurrency=request.usageConcurrency,
        close_client=True,
    )
    return {"apps": len(apps), "output": str(APP_USAGE_DIR)}


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


async def _execute_fetch_job(job_id: str, request: FetchJobRequest, steps: list[FetchStep]) -> None:
    project_id = request.project_id
    apps_cache: list[dict[str, Any]] | None = None
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
        await _load_project_creds_to_env(project_id)
        await _append_log(job_id, "✓ Credentials geladen")

        cleared = _clear_outputs_for_steps(steps)
        if cleared.get("files") or cleared.get("dirs"):
            await _append_log(job_id, "Alte Ausgabedateien bereinigt")
        await _update_job(job_id, cleanup=cleared)

        for i, step in enumerate(steps, 1):
            label = step_labels.get(step, step)
            await _append_log(job_id, f"Schritt {i}/{len(steps)}: {label}…")
            await _update_job(job_id, currentStep=step)

            if step == "spaces":
                result = await _run_spaces_step()
                await _append_log(job_id, f"✓ {result.get('count', 0)} Spaces geladen")
            elif step == "apps":
                apps_cache, result = await _run_apps_step(request)
                await _append_log(job_id, f"✓ {result.get('count', 0)} Apps geladen")
            elif step == "data-connections":
                result = await _run_data_connections_step()
                await _append_log(job_id, f"✓ {result.get('count', 0)} Datenverbindungen geladen")
            elif step == "lineage":
                if apps_cache is None:
                    apps_cache = _load_apps_inventory()
                result = await _run_lineage_step(request, apps_cache)
                await _append_log(job_id, f"✓ Lineage für {len(apps_cache)} Apps berechnet")
            elif step == "app-edges":
                if apps_cache is None:
                    apps_cache = _load_apps_inventory()
                result = await _run_app_edges_step(request, apps_cache)
                edges = result.get("appEdges", {}).get("edges", 0)
                await _append_log(job_id, f"✓ {edges} App-Kanten gefunden")
            elif step == "usage":
                if apps_cache is None:
                    apps_cache = _load_apps_inventory()
                result = await _run_usage_step(request, apps_cache)
                await _append_log(job_id, f"✓ Usage-Daten geladen")
            else:
                continue
            await _complete_job_step(job_id, step, result)

        store.load()
        await _append_log(job_id, "Speichere Daten in Datenbank…")
        db_result = await _run_db_store_step(project_id)
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


async def _load_project_creds_to_env(project_id: int) -> None:
    """Load credentials from a project's customer into os.environ for the duration of a fetch."""
    from app.database import AsyncSessionLocal
    from app.models import Customer, Project
    from sqlalchemy import select
    async with AsyncSessionLocal() as session:
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


async def _run_db_store_step(project_id: int) -> dict[str, Any]:
    """After a fetch, persist graph data as JSONB in PostgreSQL (scoped by project_id)."""
    from app.database import AsyncSessionLocal
    from app.models import QlikApp, LineageNode, LineageEdge
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stored: dict[str, int] = {"apps": 0, "nodes": 0, "edges": 0}

    try:
        async with AsyncSessionLocal() as session:
            # --- apps ---
            if APPS_INVENTORY_FILE.exists():
                payload = read_json(APPS_INVENTORY_FILE)
                apps_list = payload.get("apps", payload) if isinstance(payload, dict) else payload
                for app_data in (apps_list if isinstance(apps_list, list) else []):
                    app_id = app_data.get("appId")
                    if not app_id:
                        continue
                    stmt = pg_insert(QlikApp).values(
                        project_id=project_id,
                        app_id=app_id,
                        space_id=app_data.get("spaceId"),
                        data=app_data,
                    ).on_conflict_do_update(
                        index_elements=["project_id", "app_id"],
                        set_={"data": app_data, "space_id": app_data.get("spaceId")},
                    )
                    await session.execute(stmt)
                    stored["apps"] += 1

            # --- nodes ---
            for node_id, node in store.nodes.items():
                stmt = pg_insert(LineageNode).values(
                    project_id=project_id,
                    node_id=node_id,
                    app_id=node.get("group"),
                    node_type=node.get("type"),
                    data=dict(node),
                ).on_conflict_do_update(
                    index_elements=["project_id", "node_id"],
                    set_={"data": dict(node), "node_type": node.get("type")},
                )
                await session.execute(stmt)
                stored["nodes"] += 1

            # --- edges ---
            for edge_id, edge in store.edges.items():
                stmt = pg_insert(LineageEdge).values(
                    project_id=project_id,
                    edge_id=edge_id,
                    source_node_id=edge.get("source"),
                    target_node_id=edge.get("target"),
                    data=dict(edge),
                ).on_conflict_do_update(
                    index_elements=["project_id", "edge_id"],
                    set_={"data": dict(edge)},
                )
                await session.execute(stmt)
                stored["edges"] += 1

            await session.commit()
    except Exception as exc:
        print(f"Warning: DB store step failed: {exc}")
    return stored


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.load()
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
        filesLoaded=store.files_loaded,
        nodesCount=len(store.nodes),
        edgesCount=len(store.edges),
    )


@app.get("/api/inventory", response_model=InventoryResponse)
async def inventory(_user: str = Depends(get_current_user_id)) -> InventoryResponse:
    return store.inventory()


@app.get("/api/apps", response_model=InventoryResponse)
async def apps(_user: str = Depends(get_current_user_id)) -> InventoryResponse:
    return store.inventory()


@app.get("/api/data-connections")
async def data_connections(_user: str = Depends(get_current_user_id)):
    try:
        return store.get_data_connections()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="data connections artifact not found")
    except ValueError:
        raise HTTPException(status_code=500, detail="data connections artifact is invalid")


@app.get("/api/spaces")
async def spaces(_user: str = Depends(get_current_user_id)):
    if not SPACES_FILE.exists():
        raise HTTPException(status_code=404, detail="spaces artifact not found")
    payload = read_json(SPACES_FILE)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="spaces artifact is invalid")
    return payload


@app.get("/api/graph/app/{app_id:path}", response_model=GraphResponse)
async def graph_for_app(app_id: str, depth: int = 1, _user: str = Depends(get_current_user_id)) -> GraphResponse:
    try:
        return store.get_app_subgraph(app_id, depth)
    except KeyError:
        raise HTTPException(status_code=404, detail="app not found")


@app.get("/api/graph/all", response_model=GraphResponse)
async def graph_all(_user: str = Depends(get_current_user_id)) -> GraphResponse:
    return store.get_full_graph()


@app.get("/api/graph/db", response_model=GraphResponse)
async def graph_from_db(session: AsyncSession = Depends(get_session), _user: str = Depends(get_current_user_id)) -> GraphResponse:
    """Read all lineage graph data from PostgreSQL JSONB tables (all projects)."""
    from app.models import LineageNode, LineageEdge
    from sqlalchemy import select
    from shared.models import Node, Edge
    nodes_result = await session.execute(select(LineageNode))
    edges_result = await session.execute(select(LineageEdge))
    nodes: list[Node] = []
    for n in nodes_result.scalars():
        try:
            nodes.append(Node(**n.data))
        except Exception:
            pass
    edges: list[Edge] = []
    for e in edges_result.scalars():
        try:
            edges.append(Edge(**e.data))
        except Exception:
            pass
    return GraphResponse(nodes=nodes, edges=edges)


@app.get("/api/graph/project/{project_id}", response_model=GraphResponse)
async def graph_for_project(project_id: int, session: AsyncSession = Depends(get_session), _user: str = Depends(get_current_user_id)) -> GraphResponse:
    """Read lineage graph data for a specific project from PostgreSQL."""
    from app.models import LineageNode, LineageEdge
    from sqlalchemy import select
    from shared.models import Node, Edge
    nodes_result = await session.execute(
        select(LineageNode).where(LineageNode.project_id == project_id)
    )
    edges_result = await session.execute(
        select(LineageEdge).where(LineageEdge.project_id == project_id)
    )
    nodes: list[Node] = []
    for n in nodes_result.scalars():
        try:
            nodes.append(Node(**n.data))
        except Exception:
            pass
    edges: list[Edge] = []
    for e in edges_result.scalars():
        try:
            edges.append(Edge(**e.data))
        except Exception:
            pass
    return GraphResponse(nodes=nodes, edges=edges)


@app.get("/api/graph/node/{node_id:path}", response_model=GraphResponse)
async def graph_for_node(node_id: str, direction: str = "both", depth: int = 1, _user: str = Depends(get_current_user_id)) -> GraphResponse:
    if direction not in {"up", "down", "both"}:
        raise HTTPException(status_code=400, detail="invalid direction")
    result = store.get_node_subgraph(node_id, direction, depth)
    if not result["nodes"]:
        raise HTTPException(status_code=404, detail="node not found")
    return result


@app.get("/api/reports/orphans", response_model=OrphansReport)
async def orphans(_user: str = Depends(get_current_user_id)) -> OrphansReport:
    return store.orphans_report()


@app.get("/api/app/{app_id:path}/usage")
async def app_usage(app_id: str, _user: str = Depends(get_current_user_id)):
    try:
        return store.get_app_usage(app_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="usage artifact not found")
    except ValueError:
        raise HTTPException(status_code=500, detail="usage artifact is invalid")


@app.get("/api/app/{app_id:path}/script")
async def app_script(app_id: str, _user: str = Depends(get_current_user_id)):
    try:
        return store.get_app_script(app_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="script artifact not found")
    except ValueError:
        raise HTTPException(status_code=500, detail="script artifact is invalid")


@app.get("/api/fetch/status")
async def fetch_status(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_user_id),
):
    from app.models import Customer
    from sqlalchemy import select, func as sa_func
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
async def list_fetch_jobs(_user: str = Depends(get_current_user_id)):
    async with fetch_jobs_lock:
        jobs = [_public_job(job) for job in fetch_jobs_registry.values()]
    jobs.sort(key=lambda item: item.get("updatedAt", ""), reverse=True)
    return {"jobs": jobs[:25]}


@app.get("/api/fetch/jobs/{job_id}")
async def get_fetch_job(job_id: str, _user: str = Depends(get_current_user_id)):
    async with fetch_jobs_lock:
        job = fetch_jobs_registry.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="fetch job not found")
        return _public_job(job)


@app.get("/api/fetch/jobs/{job_id}/logs")
async def get_fetch_job_logs(job_id: str, _user: str = Depends(get_current_user_id)):
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
    _user: str = Depends(get_current_user_id),
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
        }
        fetch_jobs_registry[job_id] = job
        _prune_old_jobs()

    task = asyncio.create_task(_execute_fetch_job(job_id, payload, planned_steps))
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
