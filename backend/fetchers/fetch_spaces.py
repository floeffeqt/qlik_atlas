from typing import Any, Dict, List, Optional, Tuple

from shared.qlik_client import QlikClient, resolve_logger


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    items = payload.get("data")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    items = payload.get("spaces")
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


def _normalize_space(item: Dict[str, Any]) -> Dict[str, Any]:
    space_id = item.get("id") or item.get("spaceId")
    name = item.get("name") or item.get("spaceName")
    space_type = item.get("type") or item.get("spaceType")
    tenant_id = item.get("tenantId") or item.get("tenant_id")
    owner_id = item.get("ownerId") or item.get("owner_id")
    created_at = item.get("createdAt") or item.get("created_at")
    updated_at = item.get("updatedAt") or item.get("updated_at")
    return {
        "spaceId": str(space_id or ""),
        "spaceName": str(name or space_id or ""),
        "type": str(space_type or ""),
        "tenantId": str(tenant_id or ""),
        "ownerId": str(owner_id or ""),
        "createdAt": created_at,
        "updatedAt": updated_at,
    }


async def fetch_all_spaces(
    client: QlikClient,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    logger = resolve_logger(getattr(client, "logger", None), "qlik.fetch.spaces")
    spaces: List[Dict[str, Any]] = []
    seen_ids = set()
    next_url: Optional[str] = None
    offset = 0

    while True:
        if next_url:
            logger.info("Fetching spaces page via next link")
            data, _ = await client.get_json(next_url)
        else:
            params = {"limit": limit, "offset": offset}
            logger.info("Fetching spaces page limit=%s offset=%s", limit, offset)
            data, _ = await client.get_json("/api/v1/spaces", params=params)

        if not data:
            logger.info("No data returned, stopping spaces pagination")
            break

        items = _extract_items(data)
        if not items:
            logger.info("No spaces returned, stopping pagination")
            break

        for item in items:
            normalized = _normalize_space(item)
            space_id = normalized["spaceId"]
            if not space_id or space_id in seen_ids:
                continue
            seen_ids.add(space_id)
            spaces.append(normalized)

        next_href = _next_href(data)
        if next_href:
            next_url = str(next_href)
            logger.info("Fetched so far: %s spaces", len(spaces))
            continue

        total, meta_limit, meta_offset = _pagination_meta(data)
        effective_limit = meta_limit or limit
        if total is not None and meta_offset is not None:
            next_offset = meta_offset + effective_limit
            if next_offset >= total:
                break
            offset = next_offset
            next_url = None
            logger.info("Fetched so far: %s spaces", len(spaces))
            continue

        if len(items) < effective_limit:
            break

        offset += effective_limit
        next_url = None
        logger.info("Fetched so far: %s spaces", len(spaces))

    return spaces
