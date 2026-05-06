import hashlib
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from shared.qlik_client import QlikClient, resolve_logger


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "reloads", "items"):
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


def _tenant_from_client(client: QlikClient) -> str:
    parsed = urlparse(client.base_url)
    return parsed.netloc or parsed.path or client.base_url


def _stable_reload_id(item: Dict[str, Any]) -> str:
    explicit = item.get("id") or item.get("reloadId")
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    operational = item.get("operational") if isinstance(item.get("operational"), dict) else {}
    operational_id = operational.get("id")
    if operational_id is not None and str(operational_id).strip():
        return str(operational_id).strip()
    raw = "|".join(
        str(item.get(key) or "")
        for key in ("appId", "createdDate", "creationTime", "startTime", "title")
    )
    return "reload_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _normalize_reload(item: Dict[str, Any], source: str, tenant: str) -> Dict[str, Any]:
    operational = item.get("operational") if isinstance(item.get("operational"), dict) else {}
    links = item.get("links") if isinstance(item.get("links"), dict) else {}
    self_link = links.get("self") or links.get("Self") or {}
    if not isinstance(self_link, dict):
        self_link = {}

    return {
        "id": _stable_reload_id(item),
        "log": item.get("log"),
        "type": item.get("type"),
        "status": item.get("status"),
        "userId": item.get("userId"),
        "weight": item.get("weight"),
        "endTime": item.get("endTime"),
        "partial": item.get("partial"),
        "tenantId": item.get("tenantId"),
        "errorCode": item.get("errorCode"),
        "errorMessage": item.get("errorMessage"),
        "startTime": item.get("startTime"),
        "engineTime": item.get("engineTime"),
        "creationTime": item.get("creationTime"),
        "createdDate": item.get("createdDate"),
        "modifiedDate": item.get("modifiedDate"),
        "modifiedByUserName": item.get("modifiedByUserName"),
        "ownerId": item.get("ownerId"),
        "title": item.get("title"),
        "description": item.get("description"),
        "appId": item.get("appId"),
        "logAvailable": item.get("logAvailable"),
        "operational_id": operational.get("id"),
        "operational_nextExecution": operational.get("nextExecution"),
        "operational_timesExecuted": operational.get("timesExecuted"),
        "operational_state": operational.get("state"),
        "operational_hash": operational.get("hash"),
        "links_self_href": self_link.get("href") or self_link.get("Href"),
        "source": source,
        "tenant": tenant,
    }


async def fetch_all_reloads(
    client: QlikClient,
    limit: int = 100,
    app_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    logger = resolve_logger(getattr(client, "logger", None), "qlik.fetch.reloads")
    reloads: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    next_url: Optional[str] = None
    next_token: Optional[str] = None
    offset = 0
    tenant = _tenant_from_client(client)
    source = "/api/v1/reloads"

    while True:
        if next_url:
            logger.info("Fetching reloads page via next link")
            data, _ = await client.get_json(next_url)
        else:
            params: Dict[str, Any] = {"limit": limit}
            if app_id:
                params["appId"] = app_id
            if next_token:
                params["next"] = next_token
            elif offset:
                params["offset"] = offset
            logger.info("Fetching reloads page limit=%s offset=%s", limit, offset)
            data, _ = await client.get_json("/api/v1/reloads", params=params)

        if not data:
            logger.info("No data returned, stopping reloads pagination")
            break

        items = _extract_items(data)
        if not items:
            logger.info("No reloads returned, stopping pagination")
            break

        for item in items:
            normalized = _normalize_reload(item, source=source, tenant=tenant)
            reload_id = str(normalized.get("id") or "").strip()
            if not reload_id:
                continue
            if reload_id in seen_ids:
                continue
            seen_ids.add(reload_id)
            reloads.append(normalized)

        next_href = _next_href(data)
        if next_href:
            next_url = str(next_href)
            next_token = None
            logger.info("Fetched so far: %s reloads", len(reloads))
            continue

        next_token = _next_token(data)
        if next_token:
            next_url = None
            logger.info("Fetched so far: %s reloads", len(reloads))
            continue

        total, meta_limit, meta_offset = _pagination_meta(data)
        effective_limit = meta_limit or limit
        if total is not None and meta_offset is not None and effective_limit:
            next_offset = meta_offset + effective_limit
            if next_offset >= total:
                break
            offset = next_offset
            next_url = None
            next_token = None
            logger.info("Fetched so far: %s reloads", len(reloads))
            continue

        if not effective_limit or len(items) < effective_limit:
            break

        offset += effective_limit
        next_url = None
        next_token = None
        logger.info("Fetched so far: %s reloads", len(reloads))

    return reloads
