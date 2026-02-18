import asyncio
import os
from pathlib import Path
from typing import Optional

from fetchers.fetch_apps import fetch_all_apps
from shared.qlik_client import QlikClient
from shared.utils import ensure_dir, write_json


DEFAULT_OUT_JSON = Path("../output/apps_inventory.json")


def _optional_int(value: str) -> Optional[int]:
    value = value.strip()
    return int(value) if value else None


def _build_client() -> QlikClient:
    tenant_url = os.getenv("QLIK_TENANT_URL", "").strip()
    api_key = os.getenv("QLIK_API_KEY", "").strip()
    if not tenant_url or not api_key:
        raise RuntimeError("Missing env vars QLIK_TENANT_URL or QLIK_API_KEY")
    return QlikClient(
        base_url=tenant_url,
        api_key=api_key,
        timeout=float(os.getenv("QLIK_TIMEOUT", "30")),
        max_retries=int(os.getenv("QLIK_MAX_RETRIES", "5")),
    )


async def _run() -> None:
    limit_apps = _optional_int(os.getenv("FETCH_LIMIT_APPS", ""))
    only_space = os.getenv("FETCH_ONLY_SPACE", "").strip() or None
    out_json = Path(os.getenv("APPS_OUT_JSON", str(DEFAULT_OUT_JSON)))

    client = _build_client()
    try:
        apps = await fetch_all_apps(client, limit_apps=limit_apps, only_space=only_space)
    finally:
        await client.close()

    ensure_dir(out_json.parent)
    write_json(out_json, {"count": len(apps), "apps": apps})
    print(f"Fetched apps: {len(apps)} -> {out_json}")


if __name__ == "__main__":
    asyncio.run(_run())
