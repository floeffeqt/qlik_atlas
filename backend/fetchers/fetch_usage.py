from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from shared.qlik_client import QlikApiError, QlikClient, resolve_logger
from shared.utils import ensure_dir, sanitize_name, write_json


DEFAULT_WINDOW_DAYS = 90
DEFAULT_OUTDIR = Path("./output/appusage")
DEFAULT_CONCURRENCY = int(os.getenv("QLIK_USAGE_CONCURRENCY", "5"))
DEFAULT_PAGE_LIMIT = int(os.getenv("QLIK_AUDIT_PAGE_LIMIT", "500"))

CORE_EVENT_TYPES = {
    "sheet_view": "com.qlik.v1.analytics.analytics-app-client.sheet-view.opened",
    "app_open": "com.qlik.v1.analytics.analytics-app-client.app.opened",
    "reload_finished": "com.qlik.v1.app.reload.finished",
}

CONNECTION_KEYWORDS = (
    "data-connection",
    "dataconnection",
    "data_connection",
    "data-source",
)


def _get_logger(logger: Optional[logging.Logger]) -> logging.Logger:
    return resolve_logger(logger, "qlik.fetch.usage")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e12:
            seconds /= 1000.0
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return None


def _extract_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    payload = event.get("payload")
    if isinstance(payload, dict):
        return payload
    payload = event.get("data")
    if isinstance(payload, dict):
        return payload
    payload = event.get("details")
    if isinstance(payload, dict):
        return payload
    return {}


def _extract_event_time(event: Dict[str, Any]) -> Optional[datetime]:
    for key in ("time", "timestamp", "createdAt", "eventTime", "startTime", "endTime"):
        dt = _parse_time(event.get(key))
        if dt:
            return dt
    payload = _extract_payload(event)
    for key in ("time", "timestamp", "createdAt", "eventTime", "startTime", "endTime"):
        dt = _parse_time(payload.get(key))
        if dt:
            return dt
    return None


def _extract_event_type(event: Dict[str, Any]) -> Optional[str]:
    for key in ("eventType", "type", "event_type"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value
    payload = _extract_payload(event)
    for key in ("eventType", "type", "event_type"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _normalize_app_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("qri:app:sense://"):
            return text.split("qri:app:sense://", 1)[1]
        return text
    return str(value)


def _event_matches_app(event: Dict[str, Any], app_id: str) -> bool:
    candidates: List[Any] = []
    for key in ("appId", "resourceId", "resource", "app", "object", "resourceQri", "qri"):
        value = event.get(key)
        if isinstance(value, dict):
            for inner in ("id", "appId", "resourceId"):
                if inner in value:
                    candidates.append(value.get(inner))
        else:
            candidates.append(value)

    payload = _extract_payload(event)
    for key in ("appId", "resourceId", "app", "resource"):
        value = payload.get(key)
        if isinstance(value, dict):
            for inner in ("id", "appId", "resourceId"):
                if inner in value:
                    candidates.append(value.get(inner))
        else:
            candidates.append(value)

    for cand in candidates:
        cand_id = _normalize_app_id(cand)
        if cand_id and cand_id == app_id:
            return True
    return False


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "events", "items", "audits"):
            items = payload.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    return []


def _next_href(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    links = payload.get("links") or {}
    next_link = links.get("next") or {}
    href = next_link.get("href")
    if isinstance(href, str) and href.strip():
        return href
    return None


def _next_token(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    token = payload.get("next")
    if isinstance(token, str) and token.strip():
        return token
    return None


def _pagination_meta(payload: Any) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    if not isinstance(payload, dict):
        return None, None, None
    meta = payload.get("meta") or payload.get("pagination") or {}
    total = meta.get("total") or payload.get("total")
    limit = meta.get("limit") or payload.get("limit")
    offset = meta.get("offset") or payload.get("offset")
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None
    try:
        limit = int(limit) if limit is not None else None
    except (TypeError, ValueError):
        limit = None
    try:
        offset = int(offset) if offset is not None else None
    except (TypeError, ValueError):
        offset = None
    return total, limit, offset


def _build_param_candidates(
    event_type: str, start_iso: str, end_iso: str, app_id: str, limit: int
) -> List[Dict[str, Any]]:
    filter_parts = [
        f'eventType eq "{event_type}"',
        f'time ge "{start_iso}"',
        f'time le "{end_iso}"',
    ]
    if app_id:
        filter_parts.insert(1, f'(resourceId eq "{app_id}" or appId eq "{app_id}")')
    filter_str = " and ".join(filter_parts)

    candidates: List[Dict[str, Any]] = [{"filter": filter_str, "limit": limit}]
    params = {"eventType": event_type, "from": start_iso, "to": end_iso, "limit": limit}
    if app_id:
        params["appId"] = app_id
    candidates.append(params)
    params = {"eventType": event_type, "start": start_iso, "end": end_iso, "limit": limit}
    if app_id:
        params["resourceId"] = app_id
    candidates.append(params)
    params = {"type": event_type, "from": start_iso, "to": end_iso, "limit": limit}
    if app_id:
        params["appId"] = app_id
    candidates.append(params)
    return candidates


def _filter_events(events: List[Dict[str, Any]], event_type: str, app_id: str) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for event in events:
        if event_type:
            etype = _extract_event_type(event)
            if etype and etype != event_type:
                continue
        if app_id and not _event_matches_app(event, app_id):
            continue
        filtered.append(event)
    return filtered


def _coerce_user(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("id", "userId", "user_id", "name", "email", "subject"):
            val = value.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _extract_user_id(event: Dict[str, Any]) -> Optional[str]:
    for key in ("userId", "user_id", "user", "subject", "actor", "principal", "username"):
        user = _coerce_user(event.get(key))
        if user:
            return user
    payload = _extract_payload(event)
    for key in ("userId", "user_id", "user", "subject", "actor", "principal", "username"):
        user = _coerce_user(payload.get(key))
        if user:
            return user
    return None


def _find_first_key(obj: Any, keys: Sequence[str], depth: int = 3) -> Optional[Any]:
    if depth < 0:
        return None
    keys_lower = {k.lower() for k in keys}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in keys_lower and isinstance(value, (str, int, float)):
                return value
        for value in obj.values():
            found = _find_first_key(value, keys, depth - 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_first_key(value, keys, depth - 1)
            if found is not None:
                return found
    return None


def _find_container(obj: Any, keys: Sequence[str], depth: int = 3) -> Optional[Dict[str, Any]]:
    if depth < 0:
        return None
    keys_lower = {k.lower() for k in keys}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in keys_lower and isinstance(value, dict):
                return value
        for value in obj.values():
            found = _find_container(value, keys, depth - 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_container(value, keys, depth - 1)
            if found is not None:
                return found
    return None


def _extract_connection_key(event: Dict[str, Any]) -> Optional[str]:
    primary_keys = (
        "connectionId",
        "dataConnectionId",
        "connection_id",
        "data_connection_id",
    )
    name_keys = (
        "connectionName",
        "connection",
        "dataConnection",
        "data_connection",
        "dataSource",
        "data_source",
        "name",
    )

    value = _find_first_key(event, primary_keys)
    if value is not None:
        return str(value)

    payload = _extract_payload(event)
    container = _find_container(payload, ("connection", "dataConnection", "data_connection", "dataSource", "data_source"))
    if container:
        value = _find_first_key(container, primary_keys) or _find_first_key(container, name_keys)
        if value is not None:
            return str(value)

    value = _find_first_key(payload, name_keys)
    if value is not None:
        return str(value)

    if container:
        value = _find_first_key(container, ("id",))
        if value is not None:
            return str(value)

    return None


def _strip_script_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"(?m)^\s*//.*$", "", text)
    text = re.sub(r"(?m)^\s*REM\s+.*$", "", text, flags=re.I)
    return text


def _clean_connection_name(raw: str) -> str:
    name = raw.strip().strip(";").strip()
    if (name.startswith("'") and name.endswith("'")) or (name.startswith('"') and name.endswith('"')):
        name = name[1:-1]
    if name.startswith("[") and name.endswith("]"):
        name = name[1:-1]
    return name.strip()


def _extract_connections_from_script(text: Optional[str]) -> List[str]:
    if not text:
        return []
    cleaned = _strip_script_comments(text)
    patterns = [
        re.compile(r"\bLIB\s+CONNECT\s+TO\s+([^;\n]+)", re.IGNORECASE),
        re.compile(r"\bCONNECT\s+TO\s+([^;\n]+)", re.IGNORECASE),
    ]
    found: List[str] = []
    for pattern in patterns:
        for match in pattern.findall(cleaned):
            name = _clean_connection_name(match)
            if name:
                found.append(name)
    seen = set()
    result: List[str] = []
    for name in found:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _get_load_script(app: Dict[str, Any], app_id: str, app_name: str) -> Optional[str]:
    for key in ("loadScript", "load_script", "script", "appLoadScript", "loadScriptText"):
        value = app.get(key)
        if isinstance(value, str) and value.strip():
            return value

    for key in ("loadScriptPath", "scriptPath", "load_script_path", "loadScriptFile"):
        path_value = app.get(key)
        if isinstance(path_value, str) and path_value.strip():
            candidate = Path(path_value)
            if candidate.exists():
                return candidate.read_text(encoding="utf-8")

    script_dir = os.getenv("QLIK_LOAD_SCRIPT_DIR", "").strip()
    if script_dir:
        base = Path(script_dir)
        if base.exists() and base.is_dir():
            for name in (app_id, app_name):
                if not name:
                    continue
                for suffix in (".qvs", ".txt"):
                    candidate = base / f"{name}{suffix}"
                    if candidate.exists():
                        return candidate.read_text(encoding="utf-8")

    return None


def _max_event_time(events: Iterable[Dict[str, Any]]) -> Optional[datetime]:
    max_dt: Optional[datetime] = None
    for event in events:
        dt = _extract_event_time(event)
        if dt and (max_dt is None or dt > max_dt):
            max_dt = dt
    return max_dt


def _collect_users(events: Iterable[Dict[str, Any]]) -> List[str]:
    users = set()
    for event in events:
        user = _extract_user_id(event)
        if user:
            users.add(user)
    return list(users)


async def _fetch_audit_types(client: QlikClient, logger: logging.Logger) -> List[str]:
    try:
        data, _ = await client.get_json("/api/v1/audits/types")
    except QlikApiError as exc:
        logger.warning("Failed to fetch audit types: %s", exc)
        return []
    except Exception as exc:
        logger.warning("Failed to fetch audit types: %s", exc)
        return []

    types: List[str] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("data", "types", "items"):
            items = data.get(key)
            if isinstance(items, list):
                break
        else:
            items = None
    else:
        items = None

    if isinstance(items, list):
        for item in items:
            if isinstance(item, str):
                types.append(item)
            elif isinstance(item, dict):
                for key in ("id", "name", "type", "eventType"):
                    value = item.get(key)
                    if isinstance(value, str):
                        types.append(value)
                        break

    if isinstance(data, dict) and not types:
        for key in ("type", "eventType"):
            value = data.get(key)
            if isinstance(value, str):
                types.append(value)

    seen = set()
    result: List[str] = []
    for value in types:
        value = value.strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


async def _fetch_audits_with_params(
    client: QlikClient, params: Dict[str, Any], logger: logging.Logger
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    next_url: Optional[str] = None
    next_token: Optional[str] = None
    offset: Optional[int] = None

    limit = params.get("limit")
    base_params = dict(params)

    while True:
        if next_url:
            data, _ = await client.get_json(next_url)
        else:
            request_params = dict(base_params)
            if next_token:
                request_params["next"] = next_token
                request_params.pop("offset", None)
            elif offset is not None:
                request_params["offset"] = offset
            data, _ = await client.get_json("/api/v1/audits", params=request_params)

        items = _extract_items(data)
        events.extend(items)

        next_url = _next_href(data)
        if next_url:
            continue

        next_token = _next_token(data)
        if next_token:
            continue

        total, meta_limit, meta_offset = _pagination_meta(data)
        effective_limit = meta_limit or limit
        if total is not None and meta_offset is not None and effective_limit:
            next_offset = meta_offset + effective_limit
            if next_offset >= total:
                break
            offset = next_offset
            continue

        if not effective_limit or len(items) < effective_limit:
            break
        offset = (offset or 0) + effective_limit

    return events


async def _fetch_audit_events(
    client: QlikClient,
    event_type: str,
    app_id: str,
    start_iso: str,
    end_iso: str,
    logger: logging.Logger,
) -> List[Dict[str, Any]]:
    candidates = _build_param_candidates(event_type, start_iso, end_iso, app_id, DEFAULT_PAGE_LIMIT)
    last_error: Optional[Exception] = None
    for params in candidates:
        try:
            events = await _fetch_audits_with_params(client, params, logger)
            return _filter_events(events, event_type, app_id)
        except QlikApiError as exc:
            last_error = exc
            if exc.status_code in (400, 404, 422):
                continue
            logger.warning("Audit query failed (%s) for %s: %s", exc.status_code, event_type, exc)
            return []
        except Exception as exc:
            last_error = exc
            logger.warning("Audit query failed for %s: %s", event_type, exc)
            return []

    if last_error:
        logger.warning("Audit query formats failed for %s: %s", event_type, last_error)
    return []


async def _process_app(
    idx: int,
    total: int,
    app: Dict[str, Any],
    client: QlikClient,
    semaphore: asyncio.Semaphore,
    logger: logging.Logger,
    start_iso: str,
    end_iso: str,
    window_days: int,
    core_types: Dict[str, str],
    connection_types: List[str],
    outdir: Optional[Path],
    collector: Optional[List[Dict[str, Any]]] = None,
) -> None:
    app_id = str(app.get("appId") or app.get("id") or "").strip()
    if not app_id:
        logger.warning("[%s/%s] app missing appId, skipping", idx, total)
        return
    app_name = str(app.get("appName") or app.get("name") or app_id)

    async with semaphore:
        logger.info("[%s/%s] usage %s (%s) -> start", idx, total, app_name, app_id)

        sheet_events: List[Dict[str, Any]] = []
        app_open_events: List[Dict[str, Any]] = []
        reload_events: List[Dict[str, Any]] = []

        if core_types.get("sheet_view"):
            sheet_events = await _fetch_audit_events(
                client, core_types["sheet_view"], app_id, start_iso, end_iso, logger
            )
        if core_types.get("app_open"):
            app_open_events = await _fetch_audit_events(
                client, core_types["app_open"], app_id, start_iso, end_iso, logger
            )
        if core_types.get("reload_finished"):
            reload_events = await _fetch_audit_events(
                client, core_types["reload_finished"], app_id, start_iso, end_iso, logger
            )

        sheet_views = len(sheet_events)
        app_opens = len(app_open_events)
        reloads = len(reload_events)

        user_ids = _collect_users(sheet_events + app_open_events)
        unique_users = len(user_ids)

        last_viewed_dt = _max_event_time(sheet_events + app_open_events)
        last_reload_dt = _max_event_time(reload_events)

        last_viewed_at = _to_iso(last_viewed_dt) if last_viewed_dt else None
        last_reload_at = _to_iso(last_reload_dt) if last_reload_dt else None

        if sheet_views > 0:
            classification = "actively_consumed"
        elif reloads > 0:
            classification = "technically_active"
        else:
            classification = "inactive"

        connection_entries: List[Dict[str, Any]] = []
        connection_stats: Dict[str, Optional[datetime]] = {}
        missing_connection_keys = 0

        if connection_types:
            for event_type in connection_types:
                events = await _fetch_audit_events(client, event_type, app_id, start_iso, end_iso, logger)
                for event in events:
                    conn_key = _extract_connection_key(event)
                    if not conn_key:
                        missing_connection_keys += 1
                        continue
                    dt = _extract_event_time(event)
                    if conn_key not in connection_stats:
                        connection_stats[conn_key] = dt
                    else:
                        current = connection_stats[conn_key]
                        if dt and (current is None or dt > current):
                            connection_stats[conn_key] = dt

        if connection_stats:
            for conn_key, dt in sorted(connection_stats.items(), key=lambda item: item[0]):
                last_seen = _to_iso(dt) if dt else (last_reload_at if reloads > 0 else None)
                connection_entries.append(
                    {
                        "connectionKey": conn_key,
                        "source": "audit",
                        "reloadsUsingConnection": reloads,
                        "lastSeenAt": last_seen,
                    }
                )
        else:
            script_text = _get_load_script(app, app_id, app_name)
            inferred = _extract_connections_from_script(script_text)
            if inferred and reloads > 0:
                for conn_key in inferred:
                    connection_entries.append(
                        {
                            "connectionKey": conn_key,
                            "source": "inferred",
                            "reloadsUsingConnection": reloads,
                            "lastSeenAt": last_reload_at,
                        }
                    )

        if missing_connection_keys:
            logger.warning(
                "[%s/%s] %s (%s) -> %s connection events without key",
                idx,
                total,
                app_name,
                app_id,
                missing_connection_keys,
            )

        payload = {
            "appId": app_id,
            "appName": app_name,
            "windowDays": window_days,
            "generatedAt": _to_iso(_utc_now()),
            "usage": {
                "sheetViews": sheet_views,
                "appOpens": app_opens,
                "uniqueUsers": unique_users,
                "lastViewedAt": last_viewed_at,
                "reloads": reloads,
                "lastReloadAt": last_reload_at,
                "classification": classification,
            },
            "connections": connection_entries,
        }

        file_name = f"{sanitize_name(app_name)}__{app_id}.json"
        out_path = None
        if outdir is not None:
            out_path = outdir / file_name
            write_json(out_path, payload)
        if collector is not None:
            payload["_artifactFileName"] = file_name
            collector.append(payload)
        logger.info(
            "[%s/%s] usage %s (%s) -> views=%s reloads=%s connections=%s -> %s",
            idx,
            total,
            app_name,
            app_id,
            sheet_views,
            reloads,
            len(connection_entries),
            out_path or "memory",
        )


def _resolve_window_days(value: Optional[int]) -> int:
    if value is not None:
        return int(value)
    env_value = os.getenv("QLIK_USAGE_WINDOW_DAYS", "").strip()
    if env_value:
        try:
            return int(env_value)
        except ValueError:
            return DEFAULT_WINDOW_DAYS
    return DEFAULT_WINDOW_DAYS


def _build_default_client(logger: Optional[logging.Logger]) -> QlikClient:
    tenant_url = os.getenv("QLIK_TENANT_URL", "").strip()
    api_key = os.getenv("QLIK_API_KEY", "").strip()
    if not tenant_url or not api_key:
        raise RuntimeError("Missing env vars QLIK_TENANT_URL or QLIK_API_KEY")
    max_retries = int(os.getenv("QLIK_MAX_RETRIES", "5"))
    timeout = float(os.getenv("QLIK_TIMEOUT", "30"))
    return QlikClient(
        base_url=tenant_url,
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
        logger=logger,
    )


async def fetch_usage_async(
    apps: List[Dict[str, Any]],
    client: QlikClient,
    window_days: Optional[int] = None,
    outdir: Path | str | None = DEFAULT_OUTDIR,
    concurrency: Optional[int] = None,
    close_client: bool = True,
    logger: Optional[logging.Logger] = None,
    collector: Optional[List[Dict[str, Any]]] = None,
) -> None:
    resolved_logger = _get_logger(logger or getattr(client, "logger", None))
    resolved_outdir: Optional[Path]
    if outdir is None:
        resolved_outdir = None
    else:
        resolved_outdir = Path(outdir)
        ensure_dir(resolved_outdir)

    window_days = _resolve_window_days(window_days)
    end = _utc_now()
    start = end - timedelta(days=window_days)
    start_iso = _to_iso(start)
    end_iso = _to_iso(end)

    types = await _fetch_audit_types(client, resolved_logger)
    available = set(types)
    core_types = {k: v for k, v in CORE_EVENT_TYPES.items() if v in available}
    connection_types = [t for t in types if any(k in t.lower() for k in CONNECTION_KEYWORDS)]

    if not core_types and not connection_types:
        resolved_logger.warning("No relevant audit event types found; outputs will be inactive")

    sem = asyncio.Semaphore(concurrency or DEFAULT_CONCURRENCY)
    tasks = []
    total = len(apps)
    for idx, app in enumerate(apps, start=1):
        tasks.append(
            _process_app(
                idx,
                total,
                app,
                client,
                sem,
                resolved_logger,
                start_iso,
                end_iso,
                window_days,
                core_types,
                connection_types,
                resolved_outdir,
                collector,
            )
        )

    await asyncio.gather(*tasks)
    if close_client:
        await client.close()


def fetch_usage(
    apps: List[Dict[str, Any]],
    *,
    client: Optional[QlikClient] = None,
    window_days: Optional[int] = None,
    outdir: Path | str = DEFAULT_OUTDIR,
    concurrency: Optional[int] = None,
    logger: Optional[logging.Logger] = None,
) -> None:
    close_client = False
    if client is None:
        client = _build_default_client(logger)
        close_client = True
    try:
        asyncio.run(
            fetch_usage_async(
                apps=apps,
                client=client,
                window_days=window_days,
                outdir=outdir,
                concurrency=concurrency,
                close_client=close_client,
                logger=logger,
            )
        )
    except RuntimeError as exc:
        if "asyncio.run() cannot be called" in str(exc):
            raise RuntimeError("fetch_usage() cannot be called from a running event loop; use fetch_usage_async") from exc
        raise
