from typing import Any, Dict, List, Optional, Tuple

from shared.qlik_client import QlikClient, resolve_logger


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    items = payload.get("data")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    items = payload.get("connections")
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


async def fetch_all_data_connections(
    client: QlikClient,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    logger = resolve_logger(getattr(client, "logger", None), "qlik.fetch.data_connections")
    connections: List[Dict[str, Any]] = []
    next_url: Optional[str] = None
    offset = 0

    while True:
        if next_url:
            logger.info("Fetching data connections page via next link")
            data, _ = await client.get_json(next_url)
        else:
            params = {"limit": limit, "offset": offset}
            logger.info("Fetching data connections page limit=%s offset=%s", limit, offset)
            data, _ = await client.get_json("/api/v1/data-connections", params=params)

        if not data:
            logger.info("No data returned, stopping data connections pagination")
            break

        items = _extract_items(data)
        if not items:
            logger.info("No data connections returned, stopping pagination")
            break

        connections.extend(items)

        next_href = _next_href(data)
        if next_href:
            next_url = str(next_href)
            logger.info("Fetched so far: %s data connections", len(connections))
            continue

        total, meta_limit, meta_offset = _pagination_meta(data)
        effective_limit = meta_limit or limit
        if total is not None and meta_offset is not None:
            next_offset = meta_offset + effective_limit
            if next_offset >= total:
                break
            offset = next_offset
            next_url = None
            logger.info("Fetched so far: %s data connections", len(connections))
            continue

        if len(items) < effective_limit:
            break

        offset += effective_limit
        next_url = None
        logger.info("Fetched so far: %s data connections", len(connections))

    return connections
