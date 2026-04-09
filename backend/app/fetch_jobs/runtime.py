from __future__ import annotations

import asyncio
import os
from typing import Any, Protocol

from fetchers.fetch_app_data_metadata import fetch_app_data_metadata
from fetchers.fetch_apps import fetch_all_apps
from fetchers.fetch_audits import fetch_all_audits
from fetchers.fetch_data_connections import fetch_all_data_connections
from fetchers.fetch_licenses_consumption import fetch_all_licenses_consumption
from fetchers.fetch_licenses_status import fetch_all_licenses_status
from fetchers.fetch_lineage import fetch_app_edges_for_apps, fetch_lineage_for_apps
from fetchers.fetch_reloads import fetch_all_reloads
from fetchers.fetch_spaces import fetch_all_spaces
from fetchers.fetch_usage import fetch_usage_async
from shared.qlik_client import QlikClient, QlikCredentials
from shared.qlik_engine_client import QlikEngineClient, QlikEngineError


class FetchJobRequestLike(Protocol):
    limitApps: int | None
    onlySpace: str | None
    lineageConcurrency: int | None
    lineageLevel: str
    usageConcurrency: int | None
    usageWindowDays: int | None


def _build_qlik_client(creds: QlikCredentials) -> QlikClient:
    return QlikClient(
        base_url=creds.tenant_url,
        api_key=creds.api_key,
        timeout=float(os.getenv("QLIK_TIMEOUT", "30")),
        max_retries=int(os.getenv("QLIK_MAX_RETRIES", "5")),
    )


def _extract_successful_lineage_app_ids_from_payloads(payloads: list[dict[str, Any]] | None) -> set[str]:
    app_ids: set[str] = set()
    if not isinstance(payloads, list):
        return app_ids
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        app_obj = payload.get("app")
        endpoints = payload.get("endpoints")
        if not isinstance(app_obj, dict) or not isinstance(endpoints, dict):
            continue
        source = endpoints.get("source")
        overview = endpoints.get("overview")
        if not isinstance(source, dict) or not isinstance(overview, dict):
            continue
        source_status = source.get("status")
        overview_status = overview.get("status")
        source_ok = isinstance(source_status, int) and 200 <= source_status < 300
        overview_ok = isinstance(overview_status, int) and 200 <= overview_status < 300
        if not (source_ok and overview_ok):
            continue
        app_id = app_obj.get("id")
        if app_id:
            app_ids.add(str(app_id))
    return app_ids


def _select_apps_for_app_edges(
    apps: list[dict[str, Any]],
    lineage_payloads: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    eligible = [app for app in apps if bool(app.get("lineageSuccess"))]
    if eligible:
        return eligible, "lineage_step_runtime"

    payload_successful_app_ids = _extract_successful_lineage_app_ids_from_payloads(lineage_payloads)
    if payload_successful_app_ids:
        filtered_by_payloads: list[dict[str, Any]] = []
        for app in apps:
            app_id = app.get("appId")
            if app_id and str(app_id) in payload_successful_app_ids:
                filtered_by_payloads.append(app)
        if filtered_by_payloads:
            return filtered_by_payloads, "lineage_payload_runtime"

    return list(apps), "fallback_all_apps"


async def _run_apps_step(request: FetchJobRequestLike, creds: QlikCredentials) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = _build_qlik_client(creds)
    try:
        apps = await fetch_all_apps(client, limit_apps=request.limitApps, only_space=request.onlySpace)
    finally:
        await client.close()
    return apps, {"count": len(apps), "storage": "db-first-memory", "localArtifactWritten": False}


async def _run_spaces_step(creds: QlikCredentials) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = _build_qlik_client(creds)
    limit = int(os.getenv("FETCH_SPACES_LIMIT", "100"))
    try:
        spaces = await fetch_all_spaces(client, limit=limit)
    finally:
        await client.close()
    return spaces, {"count": len(spaces), "storage": "db-first-memory", "localArtifactWritten": False}


async def _run_data_connections_step(creds: QlikCredentials) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = _build_qlik_client(creds)
    limit = int(os.getenv("FETCH_DATA_CONNECTIONS_LIMIT", "100"))
    try:
        connections = await fetch_all_data_connections(client, limit=limit)
    finally:
        await client.close()
    return connections, {"count": len(connections), "storage": "db-first-memory", "localArtifactWritten": False}


async def _run_reloads_step(creds: QlikCredentials) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = _build_qlik_client(creds)
    limit = int(os.getenv("FETCH_RELOADS_LIMIT", "100"))
    try:
        reloads = await fetch_all_reloads(client, limit=limit)
    finally:
        await client.close()
    return reloads, {"count": len(reloads), "storage": "db-first-memory", "localArtifactWritten": False}


async def _run_audits_step(creds: QlikCredentials) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = _build_qlik_client(creds)
    limit = int(os.getenv("FETCH_AUDITS_LIMIT", "100"))
    window_days = int(os.getenv("FETCH_AUDITS_WINDOW_DAYS", "90"))
    try:
        audits = await fetch_all_audits(client, limit=limit, window_days=window_days)
    finally:
        await client.close()
    return audits, {"count": len(audits), "storage": "db-first-memory", "localArtifactWritten": False}


async def _run_licenses_consumption_step(creds: QlikCredentials) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = _build_qlik_client(creds)
    limit = int(os.getenv("FETCH_LICENSES_CONSUMPTION_LIMIT", "100"))
    try:
        consumptions = await fetch_all_licenses_consumption(client, limit=limit)
    finally:
        await client.close()
    return consumptions, {"count": len(consumptions), "storage": "db-first-memory", "localArtifactWritten": False}


async def _run_licenses_status_step(creds: QlikCredentials) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = _build_qlik_client(creds)
    try:
        statuses = await fetch_all_licenses_status(client)
    finally:
        await client.close()
    return statuses, {"count": len(statuses), "storage": "db-first-memory", "localArtifactWritten": False}


async def _run_app_data_metadata_step(
    apps: list[dict[str, Any]],
    creds: QlikCredentials,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    profiling_enabled_raw = os.getenv("FETCH_APP_DATA_METADATA_PROFILING_ENABLED", "true").strip().lower()
    profiling_enabled = profiling_enabled_raw in {"1", "true", "yes", "on"}
    app_ids = sorted({str(app.get("appId")) for app in apps if isinstance(app, dict) and app.get("appId")})
    if not app_ids:
        return [], {
            "apps": 0,
            "success": 0,
            "failed": 0,
            "profilingEnabled": profiling_enabled,
            "storage": "db-first-memory",
            "localArtifactWritten": False,
        }

    concurrency_raw = os.getenv("FETCH_APP_DATA_METADATA_CONCURRENCY", "5").strip()
    try:
        concurrency = max(1, int(concurrency_raw))
    except ValueError:
        concurrency = 5

    client = _build_qlik_client(creds)
    try:
        semaphore = asyncio.Semaphore(concurrency)
        results: list[dict[str, Any]] = []
        failed = 0

        async def _fetch_one(app_id: str) -> dict[str, Any]:
            async with semaphore:
                return await fetch_app_data_metadata(
                    app_id=app_id,
                    client=client,
                    profiling_enabled=profiling_enabled,
                )

        fetched = await asyncio.gather(*[_fetch_one(app_id) for app_id in app_ids], return_exceptions=True)
        for item in fetched:
            if isinstance(item, Exception):
                failed += 1
            elif isinstance(item, dict):
                results.append(item)

        return results, {
            "apps": len(app_ids),
            "success": len(results),
            "failed": failed,
            "profilingEnabled": profiling_enabled,
            "storage": "db-first-memory",
            "localArtifactWritten": False,
        }
    finally:
        await client.close()


async def _run_lineage_step(
    request: FetchJobRequestLike,
    apps: list[dict[str, Any]],
    creds: QlikCredentials,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lineage_concurrency = request.lineageConcurrency or int(os.getenv("QLIK_LINEAGE_CONCURRENCY", "5"))
    client = _build_qlik_client(creds)
    lineage_payloads: list[dict[str, Any]] = []
    lineage_result = await fetch_lineage_for_apps(
        client=client,
        apps=apps,
        outdir=None,
        success_outdir=None,
        concurrency=lineage_concurrency,
        collector=lineage_payloads,
    )
    return lineage_payloads, {
        "apps": len(apps),
        "lineage": lineage_result,
        "storage": "db-first-memory",
        "localArtifactWritten": False,
    }


async def _run_app_edges_step(
    request: FetchJobRequestLike,
    apps: list[dict[str, Any]],
    creds: QlikCredentials,
    lineage_payloads: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    eligible_apps, filter_source = _select_apps_for_app_edges(apps, lineage_payloads=lineage_payloads)
    if not eligible_apps:
        return [], {
            "apps": len(apps),
            "eligibleApps": 0,
            "filterSource": filter_source,
            "lineageLevel": request.lineageLevel,
            "appEdges": {"success": 0, "failed": 0, "edges": 0},
            "storage": "db-first-memory",
            "localArtifactWritten": False,
        }

    lineage_concurrency = request.lineageConcurrency or int(os.getenv("QLIK_LINEAGE_CONCURRENCY", "5"))
    client = _build_qlik_client(creds)
    app_edges_payloads: list[dict[str, Any]] = []
    edges_result = await fetch_app_edges_for_apps(
        client=client,
        apps=eligible_apps,
        outdir=None,
        success_outdir=None,
        concurrency=lineage_concurrency,
        up_depth=os.getenv("QLIK_APP_EDGES_UP_DEPTH", "-1"),
        collapse=os.getenv("QLIK_APP_EDGES_COLLAPSE", "true"),
        graph_level=request.lineageLevel,
        collector=app_edges_payloads,
    )
    return app_edges_payloads, {
        "apps": len(apps),
        "eligibleApps": len(eligible_apps),
        "filterSource": filter_source,
        "lineageLevel": request.lineageLevel,
        "appEdges": edges_result,
        "storage": "db-first-memory",
        "localArtifactWritten": False,
    }


def _build_engine_client(creds: QlikCredentials) -> QlikEngineClient:
    return QlikEngineClient(
        creds,
        timeout=float(os.getenv("QLIK_ENGINE_TIMEOUT", "30")),
    )


async def _run_scripts_step(
    apps: list[dict[str, Any]],
    creds: QlikCredentials,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch current load scripts for all apps via the Qlik Engine API (QIX/WebSocket).

    Uses GetScript on the live engine — works regardless of whether script
    versioning is enabled and requires only Can-View access to the app.
    """
    app_ids = sorted({str(app.get("appId")) for app in apps if isinstance(app, dict) and app.get("appId")})
    if not app_ids:
        return [], {"apps": 0, "success": 0, "failed": 0, "storage": "db-first-memory", "localArtifactWritten": False}

    concurrency = max(1, int(os.getenv("FETCH_SCRIPTS_CONCURRENCY", "3")))
    engine = _build_engine_client(creds)
    semaphore = asyncio.Semaphore(concurrency)
    results: list[dict[str, Any]] = []
    failed = 0

    async def _fetch_one(app_id: str) -> dict[str, Any] | None:
        async with semaphore:
            try:
                script_text = await engine.get_script(app_id)
                return {
                    "app_id": app_id,
                    "script": script_text,
                    "source": "qlik_engine",
                    "data": {"length": len(script_text)},
                }
            except QlikEngineError as exc:
                engine._logger.warning("Script fetch failed for app %s: %s", app_id, exc)
                return None
            except Exception as exc:
                engine._logger.warning("Script fetch unexpected error for app %s: %s", app_id, exc)
                return None

    fetched = await asyncio.gather(*[_fetch_one(app_id) for app_id in app_ids], return_exceptions=True)
    for item in fetched:
        if isinstance(item, Exception) or item is None:
            failed += 1
        elif isinstance(item, dict):
            results.append(item)

    return results, {
        "apps": len(app_ids),
        "success": len(results),
        "failed": failed,
        "storage": "db-first-memory",
        "localArtifactWritten": False,
    }


async def _run_usage_step(
    request: FetchJobRequestLike,
    apps: list[dict[str, Any]],
    creds: QlikCredentials,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = _build_qlik_client(creds)
    usage_window_days = request.usageWindowDays or int(os.getenv("QLIK_USAGE_WINDOW_DAYS", "28"))
    usage_concurrency = request.usageConcurrency or int(os.getenv("QLIK_USAGE_CONCURRENCY", "5"))
    try:
        usage_payloads = await fetch_usage_async(
            client=client,
            apps=apps,
            outdir=None,
            days=usage_window_days,
            concurrency=usage_concurrency,
        )
    finally:
        await client.close()
    return usage_payloads, {
        "apps": len(apps),
        "usageRecords": len(usage_payloads),
        "windowDays": usage_window_days,
        "storage": "db-first-memory",
        "localArtifactWritten": False,
    }
