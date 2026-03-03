import hashlib
from typing import Any, Dict, List
from urllib.parse import urlparse

from shared.qlik_client import QlikClient, resolve_logger


def _tenant_from_client(client: QlikClient) -> str:
    parsed = urlparse(client.base_url)
    return parsed.netloc or parsed.path or client.base_url


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    data_items = payload.get("data")
    if isinstance(data_items, list):
        return [item for item in data_items if isinstance(item, dict)]
    return [payload]


def _stable_status_id(item: Dict[str, Any]) -> str:
    explicit = item.get("id")
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    raw = "|".join(
        str(item.get(k) or "")
        for k in ("type", "trial", "valid", "origin", "status", "product", "deactivated")
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"license_status_{digest}"


def _normalize_status(item: Dict[str, Any], source: str, tenant: str) -> Dict[str, Any]:
    return {
        "id": _stable_status_id(item),
        "type": item.get("type"),
        "trial": item.get("trial"),
        "valid": item.get("valid"),
        "origin": item.get("origin"),
        "status": item.get("status"),
        "product": item.get("product"),
        "deactivated": item.get("deactivated"),
        "source": source,
        "tenant": tenant,
    }


async def fetch_all_licenses_status(
    client: QlikClient,
) -> List[Dict[str, Any]]:
    logger = resolve_logger(getattr(client, "logger", None), "qlik.fetch.licenses_status")
    source = "/api/v1/licenses/status"
    tenant = _tenant_from_client(client)

    logger.info("Fetching license status")
    data, _ = await client.get_json(source)
    if not data:
        return []

    statuses: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in _extract_items(data):
        normalized = _normalize_status(item, source=source, tenant=tenant)
        status_id = str(normalized.get("id") or "").strip()
        if not status_id or status_id in seen_ids:
            continue
        seen_ids.add(status_id)
        statuses.append(normalized)
    return statuses
