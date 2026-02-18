import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List

from fetchers.fetch_lineage import fetch_app_edges_for_apps, fetch_lineage_for_apps
from shared.qlik_client import QlikClient
from shared.utils import ensure_dir, read_json, write_json


DEFAULT_APPS_JSON = Path("../output/apps_inventory.json")
DEFAULT_LINEAGE_OUTDIR = Path("../output/lineage")
DEFAULT_LINEAGE_SUCCESS_OUTDIR = Path("../output/lineage_success")
DEFAULT_APP_EDGES_OUTDIR = DEFAULT_LINEAGE_SUCCESS_OUTDIR


def _build_client() -> QlikClient:
    tenant_url = os.getenv("QLIK_TENANT_URL", "").strip()
    api_key = os.getenv("QLIK_API_KEY", "").strip()
    if not tenant_url or not api_key:
        raise RuntimeError("Missing env vars QLIK_TENANT_URL or QLIK_API_KEY")
    return QlikClient(
        base_url=tenant_url,
        api_key=api_key,
        timeout=float(os.getenv("QLIK_TIMEOUT", "30")),
        max_retries=int(os.getenv("QLIK_MAX_RETRIES", "5")),
    )


def _load_apps(path: Path) -> List[Dict[str, Any]]:
    payload = read_json(path)
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        apps = payload.get("apps")
        if isinstance(apps, list):
            return [x for x in apps if isinstance(x, dict)]
    raise RuntimeError(f"Invalid apps source format: {path}")


def _is_http_ok(status: Any) -> bool:
    return isinstance(status, int) and 200 <= status < 300


def _extract_successful_lineage_app_ids(lineage_outdir: Path) -> set[str]:
    app_ids: set[str] = set()
    if not lineage_outdir.exists():
        return app_ids

    for path in lineage_outdir.glob("*__lineage.json"):
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


def _select_apps_for_app_edges(apps: List[Dict[str, Any]], lineage_outdir: Path) -> tuple[List[Dict[str, Any]], str]:
    eligible = [app for app in apps if bool(app.get("lineageSuccess"))]
    if eligible:
        return eligible, "lineage_step_runtime"

    successful_app_ids = _extract_successful_lineage_app_ids(lineage_outdir)
    if not successful_app_ids:
        return [], "no_successful_lineage_found"

    filtered: List[Dict[str, Any]] = []
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


async def _run() -> None:
    apps_path = Path(os.getenv("APPS_SOURCE_JSON", str(DEFAULT_APPS_JSON)))
    lineage_outdir = Path(os.getenv("LINEAGE_OUTDIR", str(DEFAULT_LINEAGE_OUTDIR)))
    success_outdir = Path(os.getenv("LINEAGE_SUCCESS_OUTDIR", str(DEFAULT_LINEAGE_SUCCESS_OUTDIR)))
    app_edges_outdir = Path(os.getenv("APP_EDGES_OUTDIR", str(DEFAULT_APP_EDGES_OUTDIR)))
    concurrency = int(os.getenv("QLIK_LINEAGE_CONCURRENCY", "5"))
    up_depth = os.getenv("QLIK_APP_EDGES_UP_DEPTH", "-1")
    collapse = os.getenv("QLIK_APP_EDGES_COLLAPSE", "true")
    with_edges = os.getenv("FETCH_APP_EDGES", "true").strip().lower() != "false"

    apps = _load_apps(apps_path)
    if not apps:
        print(f"No apps found in {apps_path}")
        return

    ensure_dir(lineage_outdir)
    _clear_lineage_artifacts(lineage_outdir)

    client = _build_client()
    lineage_result = await fetch_lineage_for_apps(
        client=client,
        apps=apps,
        outdir=lineage_outdir,
        success_outdir=None,
        concurrency=concurrency,
    )

    edges_result = None
    app_edges_eligible = 0
    app_edges_filter_source = None
    if with_edges:
        eligible_apps, app_edges_filter_source = _select_apps_for_app_edges(apps, lineage_outdir)
        app_edges_eligible = len(eligible_apps)
        ensure_dir(app_edges_outdir)
        _clear_app_edges_artifacts(app_edges_outdir)
        client = _build_client()
        if eligible_apps:
            edges_result = await fetch_app_edges_for_apps(
                client=client,
                apps=eligible_apps,
                outdir=app_edges_outdir,
                success_outdir=None,
                concurrency=concurrency,
                up_depth=up_depth,
                collapse=collapse,
            )
        else:
            await client.close()
            edges_result = {"success": 0, "failed": 0, "edges": []}

    summary = {
        "apps": len(apps),
        "lineage": lineage_result,
        "app_edges": (
            None
            if edges_result is None
            else {
                "eligible_apps": app_edges_eligible,
                "filter_source": app_edges_filter_source,
                "success": edges_result.get("success", 0),
                "failed": edges_result.get("failed", 0),
                "edges": len(edges_result.get("edges", [])),
            }
        ),
    }
    summary_path = Path("../output/lineage_run_summary.json")
    write_json(summary_path, summary)
    print(f"Fetched lineage for apps: {len(apps)} -> {lineage_outdir}")
    if with_edges:
        print(f"Fetched app edges -> {app_edges_outdir}")
    print(f"Summary -> {summary_path}")


if __name__ == "__main__":
    asyncio.run(_run())
