import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

from shared.qlik_client import QlikApiError, QlikClient, resolve_logger
from shared.utils import sanitize_name, url_encode_qri, write_json


def _encode_app_qri(app_id: str) -> str:
    qri = f"qri:app:sense://{app_id}"
    return url_encode_qri(qri)


def _source_path(app_id: str) -> str:
    encoded = _encode_app_qri(app_id)
    return f"/api/v1/lineage-graphs/impact/{encoded}/source"


def _overview_path(app_id: str) -> str:
    encoded = _encode_app_qri(app_id)
    return f"/api/v1/lineage-graphs/impact/{encoded}/overview"


def _app_edges_path(app_id: str, up_depth: str, collapse: str) -> str:
    encoded = _encode_app_qri(app_id)
    return f"/api/v1/lineage-graphs/nodes/{encoded}?level=resource&collapse={collapse}&up={up_depth}"


async def _fetch_endpoint(
    name: str,
    path: str,
    client: QlikClient,
    semaphore: asyncio.Semaphore,
    logger,
) -> Dict[str, Any]:
    async with semaphore:
        try:
            data, status = await client.get_json(path)
            if logger:
                logger.info("Endpoint %s -> %s", name, status)
            return {"status": status, "data": data}
        except QlikApiError as exc:
            msg = exc.response_text or str(exc)
            if logger:
                logger.info("Endpoint %s -> %s", name, exc.status_code)
            return {"status": exc.status_code, "error": msg}
        except Exception as exc:
            if logger:
                logger.info("Endpoint %s -> error", name)
            return {"status": 0, "error": str(exc)}


def _is_success(result: Dict[str, Any]) -> bool:
    status = result.get("status")
    return isinstance(status, int) and 200 <= status < 300


async def fetch_lineage_source(app_id: str, client: QlikClient, semaphore: asyncio.Semaphore, logger) -> Dict[str, Any]:
    return await _fetch_endpoint("source", _source_path(app_id), client, semaphore, logger)


async def fetch_lineage_overview(
    app_id: str, client: QlikClient, semaphore: asyncio.Semaphore, logger
) -> Dict[str, Any]:
    return await _fetch_endpoint("overview", _overview_path(app_id), client, semaphore, logger)


async def fetch_and_save_lineage_for_app(
    idx: int,
    total: int,
    app: Dict[str, Any],
    client: QlikClient,
    outdir,
    success_outdir,
    semaphore: asyncio.Semaphore,
    logger,
    results,
    collector=None,
) -> None:
    app_id = str(app.get("appId", ""))
    app_name = app.get("name") or app_id
    if logger:
        logger.info("[%s/%s] %s (%s) -> start", idx, total, app_name, app_id)

    source_result = await fetch_lineage_source(app_id, client, semaphore, logger)
    overview_result = await fetch_lineage_overview(app_id, client, semaphore, logger)

    lineage = {
        "app": {
            "id": app_id,
            "name": app_name,
            "spaceId": app.get("spaceId", ""),
            "itemType": app.get("itemType", ""),
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "endpoints": {
            "source": source_result,
            "overview": overview_result,
        },
    }

    file_name = f"{sanitize_name(str(app_name))}__{app_id}__lineage.json"
    out_path = None
    if outdir is not None:
        out_path = outdir / file_name
        write_json(out_path, lineage)
    if collector is not None:
        lineage["_artifactFileName"] = file_name
        collector.append(lineage)

    source_ok = _is_success(source_result)
    overview_ok = _is_success(overview_result)
    app["lineageFetched"] = source_ok or overview_ok
    app["lineageSuccess"] = source_ok and overview_ok

    if source_ok and overview_ok:
        results["success"] += 1
        if success_outdir is not None:
            success_path = success_outdir / file_name
            write_json(success_path, lineage)
            if logger:
                logger.info("[%s/%s] %s (%s) -> success copy -> %s", idx, total, app_name, app_id, success_path)
    elif source_ok or overview_ok:
        results["partial"] += 1
        results["errors"][app_id] = {
            "source": source_result if not source_ok else None,
            "overview": overview_result if not overview_ok else None,
        }
    else:
        results["failed"] += 1
        results["errors"][app_id] = {
            "source": source_result,
            "overview": overview_result,
        }

    if logger:
        logger.info(
            "[%s/%s] %s (%s) -> source=%s overview=%s -> %s",
            idx,
            total,
            app_name,
            app_id,
            source_result.get("status"),
            overview_result.get("status"),
            out_path or "memory",
        )


async def fetch_lineage_for_apps(
    client: QlikClient,
    apps: List[Dict[str, Any]],
    outdir,
    success_outdir=None,
    concurrency: int = 5,
    collector=None,
) -> Dict[str, Any]:
    semaphore = asyncio.Semaphore(concurrency)
    logger = resolve_logger(getattr(client, "logger", None), "qlik.fetch.lineage")
    results: Dict[str, Any] = {"success": 0, "partial": 0, "failed": 0, "errors": {}}

    tasks = []
    total = len(apps)
    for idx, app in enumerate(apps, start=1):
        task = fetch_and_save_lineage_for_app(
            idx, total, app, client, outdir, success_outdir, semaphore, logger, results, collector
        )
        tasks.append(task)

    await asyncio.gather(*tasks)
    await client.close()
    return results


def _extract_app_edges(data: Any) -> List[Dict[str, str]]:
    edges = data.get("edges") if isinstance(data, dict) else None
    if not isinstance(edges, list):
        return []

    result = []
    seen = set()
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = edge.get("source") or edge.get("from")
        target = edge.get("target") or edge.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if not source.startswith("qri:app:sense://"):
            continue
        if not target.startswith("qri:app:sense://"):
            continue
        key = (source, target)
        if key in seen:
            continue
        seen.add(key)
        result.append({"source": source, "target": target})
    return result


async def fetch_app_edges_for_apps(
    client: QlikClient,
    apps: List[Dict[str, Any]],
    outdir,
    success_outdir=None,
    concurrency: int = 5,
    up_depth: str = "-1",
    collapse: str = "true",
    collector=None,
) -> Dict[str, Any]:
    semaphore = asyncio.Semaphore(concurrency)
    logger = resolve_logger(getattr(client, "logger", None), "qlik.fetch.lineage")
    results: Dict[str, Any] = {"success": 0, "failed": 0, "errors": {}, "edges": []}

    async def _fetch_edges_for_app(idx: int, total: int, app: Dict[str, Any]) -> None:
        app_id = str(app.get("appId", ""))
        app_name = app.get("name") or app_id
        if logger:
            logger.info("[%s/%s] %s (%s) -> start app_edges", idx, total, app_name, app_id)

        path = _app_edges_path(app_id, up_depth, collapse)
        result = await _fetch_endpoint("app_edges", path, client, semaphore, logger)

        edges = _extract_app_edges(result.get("data") if isinstance(result, dict) else None)
        results["edges"].extend(edges)

        payload = {
            "app": {
                "id": app_id,
                "name": app_name,
                "spaceId": app.get("spaceId", ""),
                "itemType": app.get("itemType", ""),
            },
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "status": result.get("status"),
            "edges": edges,
            "raw": result.get("data") if isinstance(result, dict) and "data" in result else result,
        }

        file_name = f"{sanitize_name(str(app_name))}__{app_id}__app_edges.json"
        out_path = None
        if outdir is not None:
            out_path = outdir / file_name
            write_json(out_path, payload)
        if collector is not None:
            payload["_artifactFileName"] = file_name
            collector.append(payload)

        if isinstance(result, dict) and 200 <= int(result.get("status") or 0) < 300:
            results["success"] += 1
            if success_outdir is not None:
                success_path = success_outdir / file_name
                write_json(success_path, payload)
                if logger:
                    logger.info("[%s/%s] %s (%s) -> success copy -> %s", idx, total, app_name, app_id, success_path)
        else:
            results["failed"] += 1
            results["errors"][app_id] = result

        if logger:
            logger.info(
                "[%s/%s] %s (%s) -> status=%s edges=%s -> %s",
                idx,
                total,
                app_name,
                app_id,
                result.get("status"),
                len(edges),
                out_path or "memory",
            )

    tasks = []
    total = len(apps)
    for idx, app in enumerate(apps, start=1):
        tasks.append(_fetch_edges_for_app(idx, total, app))

    await asyncio.gather(*tasks)
    await client.close()
    return results
