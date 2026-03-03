import hashlib
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from shared.qlik_client import QlikClient, resolve_logger


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "items", "consumptions"):
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


def _stable_consumption_id(item: Dict[str, Any]) -> str:
    explicit = item.get("id")
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    session_id = item.get("sessionId")
    if session_id is not None and str(session_id).strip():
        return str(session_id).strip()
    raw = "|".join(
        str(item.get(k) or "")
        for k in ("appId", "userId", "endTime", "duration", "allotmentId", "minutesUsed", "licenseUsage")
    )
    return "consumption_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _normalize_consumption(item: Dict[str, Any], source: str, tenant: str) -> Dict[str, Any]:
    return {
        "id": _stable_consumption_id(item),
        "appId": item.get("appId"),
        "userId": item.get("userId"),
        "endTime": item.get("endTime"),
        "duration": item.get("duration"),
        "sessionId": item.get("sessionId"),
        "allotmentId": item.get("allotmentId"),
        "minutesUsed": item.get("minutesUsed"),
        "capacityUsed": item.get("capacityUsed"),
        "licenseUsage": item.get("licenseUsage"),
        "source": source,
        "tenant": tenant,
    }


async def fetch_all_licenses_consumption(
    client: QlikClient,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    logger = resolve_logger(getattr(client, "logger", None), "qlik.fetch.licenses_consumption")
    consumptions: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    next_url: Optional[str] = None
    next_token: Optional[str] = None
    offset = 0
    tenant = _tenant_from_client(client)
    source = "/api/v1/licenses/consumption"

    while True:
        if next_url:
            logger.info("Fetching license consumption page via next link")
            data, _ = await client.get_json(next_url)
        else:
            params: Dict[str, Any] = {"limit": limit}
            if next_token:
                params["next"] = next_token
            elif offset:
                params["offset"] = offset
            logger.info("Fetching license consumption page limit=%s offset=%s", limit, offset)
            data, _ = await client.get_json("/api/v1/licenses/consumption", params=params)

        if not data:
            logger.info("No data returned, stopping license consumption pagination")
            break

        items = _extract_items(data)
        if not items:
            logger.info("No license consumption records returned, stopping pagination")
            break

        for item in items:
            normalized = _normalize_consumption(item, source=source, tenant=tenant)
            record_id = str(normalized.get("id") or "").strip()
            if not record_id:
                continue
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            consumptions.append(normalized)

        next_href = _next_href(data)
        if next_href:
            next_url = str(next_href)
            next_token = None
            logger.info("Fetched so far: %s license consumption records", len(consumptions))
            continue

        next_token = _next_token(data)
        if next_token:
            next_url = None
            logger.info("Fetched so far: %s license consumption records", len(consumptions))
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
            logger.info("Fetched so far: %s license consumption records", len(consumptions))
            continue

        if not effective_limit or len(items) < effective_limit:
            break

        offset += effective_limit
        next_url = None
        next_token = None
        logger.info("Fetched so far: %s license consumption records", len(consumptions))

    return consumptions
