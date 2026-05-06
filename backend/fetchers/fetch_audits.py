import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from shared.qlik_client import QlikApiError, QlikClient, resolve_logger


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
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


def _tenant_from_client(client: QlikClient) -> str:
    parsed = urlparse(client.base_url)
    return parsed.netloc or parsed.path or client.base_url


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_start_iso(window_days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat().replace("+00:00", "Z")


def _build_param_candidates(limit: int, window_days: int) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 100))
    start_iso = _utc_start_iso(window_days)
    end_iso = _utc_now_iso()
    return [
        {"limit": safe_limit},
        {"limit": safe_limit, "from": start_iso, "to": end_iso},
        {"limit": safe_limit, "start": start_iso, "end": end_iso},
    ]


def _stable_audit_id(item: Dict[str, Any]) -> str:
    explicit = item.get("id") or item.get("eventId")
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    raw = "|".join(
        str(item.get(key) or "")
        for key in ("time", "eventTime", "eventType", "type", "subType", "actorId", "spaceId")
    )
    return "audit_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _normalize_audit(item: Dict[str, Any], source: str, tenant: str) -> Dict[str, Any]:
    links = item.get("links") if isinstance(item.get("links"), dict) else {}
    self_link = links.get("self") or links.get("Self") or {}
    if not isinstance(self_link, dict):
        self_link = {}
    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    data_obj = item.get("data") if isinstance(item.get("data"), dict) else {}
    extensions = item.get("extensions") if isinstance(item.get("extensions"), dict) else {}
    actor = extensions.get("actor") if isinstance(extensions.get("actor"), dict) else {}
    return {
        "id": _stable_audit_id(item),
        "userId": item.get("userId"),
        "eventId": item.get("eventId"),
        "tenantId": item.get("tenantId"),
        "eventTime": item.get("eventTime"),
        "eventType": item.get("eventType"),
        "links_self_href": self_link.get("href") or self_link.get("Href"),
        "extensions_actor_sub": actor.get("sub"),
        "time": item.get("time"),
        "subType": item.get("subType"),
        "spaceId": item.get("spaceId"),
        "spaceType": item.get("spaceType"),
        "category": item.get("category"),
        "type": item.get("type"),
        "actorId": item.get("actorId"),
        "actorType": item.get("actorType"),
        "origin": item.get("origin"),
        "context": item.get("context"),
        "ipAddress": item.get("ipAddress"),
        "userAgent": item.get("userAgent"),
        "properties_appId": properties.get("appId"),
        "data_message": data_obj.get("message"),
        "source": source,
        "tenant": tenant,
    }


async def fetch_all_audits(
    client: QlikClient,
    limit: int = 100,
    window_days: int = 90,
) -> List[Dict[str, Any]]:
    logger = resolve_logger(getattr(client, "logger", None), "qlik.fetch.audits")
    audits: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    next_url: Optional[str] = None
    next_token: Optional[str] = None
    offset = 0
    base_params: Optional[Dict[str, Any]] = None
    tenant = _tenant_from_client(client)
    source = "/api/v1/audits"

    while True:
        if next_url:
            logger.info("Fetching audits page via next link")
            try:
                data, _ = await client.get_json(next_url)
            except QlikApiError as exc:
                if exc.status_code in (400, 404, 422):
                    logger.warning(
                        "Stopping audits pagination: next link rejected (status=%s)", exc.status_code
                    )
                    break
                raise
        else:
            if base_params is None:
                last_error: Optional[QlikApiError] = None
                for candidate in _build_param_candidates(limit=limit, window_days=window_days):
                    params = dict(candidate)
                    if next_token:
                        params["next"] = next_token
                    elif offset:
                        params["offset"] = offset
                    logger.info("Fetching audits page with params=%s", params)
                    try:
                        data, _ = await client.get_json("/api/v1/audits", params=params)
                        base_params = dict(candidate)
                        break
                    except QlikApiError as exc:
                        last_error = exc
                        if exc.status_code in (400, 404, 422):
                            logger.warning("Audit params rejected (status=%s): %s", exc.status_code, params)
                            continue
                        raise
                else:
                    if last_error is not None:
                        if last_error.status_code in (400, 404, 422):
                            logger.warning(
                                "Audits endpoint rejected all supported parameter variants (status=%s); returning %s collected audits",
                                last_error.status_code,
                                len(audits),
                            )
                            return audits
                        raise last_error
                    raise RuntimeError("Unable to fetch audits with supported parameter variants")
            else:
                params = dict(base_params)
                if next_token:
                    params["next"] = next_token
                    params.pop("offset", None)
                elif offset:
                    params["offset"] = offset
                logger.info("Fetching audits page with params=%s", params)
                try:
                    data, _ = await client.get_json("/api/v1/audits", params=params)
                except QlikApiError as exc:
                    if exc.status_code in (400, 404, 422):
                        logger.warning(
                            "Stopping audits pagination: params rejected on follow-up page (status=%s): %s",
                            exc.status_code,
                            params,
                        )
                        break
                    raise

        if not data:
            logger.info("No data returned, stopping audits pagination")
            break

        items = _extract_items(data)
        if not items:
            logger.info("No audits returned, stopping pagination")
            break

        for item in items:
            normalized = _normalize_audit(item, source=source, tenant=tenant)
            audit_id = str(normalized.get("id") or "").strip()
            if not audit_id:
                continue
            if audit_id in seen_keys:
                continue
            seen_keys.add(audit_id)
            audits.append(normalized)

        next_href = _next_href(data)
        if next_href:
            next_url = str(next_href)
            next_token = None
            logger.info("Fetched so far: %s audits", len(audits))
            continue

        next_token = _next_token(data)
        if next_token:
            next_url = None
            logger.info("Fetched so far: %s audits", len(audits))
            continue

        total, meta_limit, meta_offset = _pagination_meta(data)
        effective_limit = meta_limit or (base_params or {}).get("limit") or limit
        if total is not None and meta_offset is not None and effective_limit:
            next_offset = meta_offset + effective_limit
            if next_offset >= total:
                break
            offset = next_offset
            next_url = None
            next_token = None
            logger.info("Fetched so far: %s audits", len(audits))
            continue

        if not effective_limit or len(items) < effective_limit:
            break

        offset += effective_limit
        next_url = None
        next_token = None
        logger.info("Fetched so far: %s audits", len(audits))

    return audits
