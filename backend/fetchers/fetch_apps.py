from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from shared.qlik_client import QlikClient, resolve_logger


async def fetch_all_apps(
    client: QlikClient,
    limit_apps: Optional[int] = None,
    only_space: Optional[str] = None,
) -> List[Dict[str, Any]]:
    logger = resolve_logger(getattr(client, "logger", None), "qlik.fetch.apps")
    apps: List[Dict[str, Any]] = []
    limit = 100
    next_url: Optional[str] = None
    seen_ids = set()
    parsed = urlparse(client.base_url)
    tenant = parsed.netloc or parsed.path or client.base_url

    while True:
        if next_url:
            logger.info("Fetching apps page via next link")
            data, _ = await client.get_json(next_url)
        else:
            params = {"resourceType": "app", "limit": limit}
            if only_space:
                params["spaceId"] = only_space
            logger.info("Fetching apps page limit=%s", limit)
            data, _ = await client.get_json("/api/v1/items", params=params)
        if not data:
            logger.info("No data returned, stopping pagination")
            break

        items = data.get("data") or []
        if not items:
            logger.info("No items returned, stopping pagination")
            break

        for item in items:
            app_id = item.get("resourceId")
            if not app_id:
                continue
            app_id = str(app_id)
            if app_id in seen_ids:
                continue
            seen_ids.add(app_id)
            item_type = item.get("resourceType") or item.get("type")
            space_id = (
                item.get("spaceId")
                or item.get("resourceAttributes", {}).get("spaceId")
                or item.get("resourceAttributes", {}).get("space_id")
            )
            name = (
                item.get("name")
                or item.get("resourceAttributes", {}).get("name")
                or item.get("resourceAttributes", {}).get("title")
                or item.get("title")
                or app_id
            )
            attrs = item.get("resourceAttributes") if isinstance(item.get("resourceAttributes"), dict) else {}
            custom_attrs = item.get("resourceCustomAttributes")
            apps.append(
                {
                    "appId": app_id,
                    "name": str(name),
                    "spaceId": str(space_id or ""),
                    "itemType": str(item_type or ""),
                    "id": item.get("id"),
                    "ownerId": item.get("ownerId"),
                    "description": item.get("description"),
                    "resourceType": item.get("resourceType"),
                    "resourceId": item.get("resourceId"),
                    "thumbnail": item.get("thumbnail"),
                    "resourceAttributes_id": attrs.get("id"),
                    "resourceAttributes_name": attrs.get("name"),
                    "resourceAttributes_description": attrs.get("description"),
                    "resourceAttributes_createdDate": attrs.get("createdDate"),
                    "resourceAttributes_modifiedDate": attrs.get("modifiedDate"),
                    "resourceAttributes_modifiedByUserName": attrs.get("modifiedByUserName"),
                    "resourceAttributes_publishTime": attrs.get("publishTime"),
                    "resourceAttributes_lastReloadTime": attrs.get("lastReloadTime"),
                    "resourceAttributes_trashed": attrs.get("trashed"),
                    "resourceCustomAttributes_json": custom_attrs if isinstance(custom_attrs, list) else [],
                    "source": "/api/v1/items",
                    "tenant": tenant,
                }
            )
            if limit_apps and len(apps) >= limit_apps:
                logger.info("Limit reached: %s apps", len(apps))
                return apps

        links = data.get("links") or {}
        next_href = (links.get("next") or {}).get("href")
        if next_href:
            next_url = str(next_href)
            logger.info("Fetched so far: %s apps", len(apps))
        else:
            logger.info("No next link, stopping pagination")
            break

    return apps
