import asyncio
import os
from pathlib import Path

from fetchers.fetch_data_connections import fetch_all_data_connections
from shared.qlik_client import QlikClient
from shared.utils import ensure_dir, write_json


DEFAULT_OUT_JSON = Path("../output/lineage/tenant_data_connections.json")


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
    limit = int(os.getenv("FETCH_DATA_CONNECTIONS_LIMIT", "100"))
    out_json = Path(os.getenv("DATA_CONNECTIONS_OUT_JSON", str(DEFAULT_OUT_JSON)))

    client = _build_client()
    try:
        connections = await fetch_all_data_connections(client, limit=limit)
    finally:
        await client.close()

    ensure_dir(out_json.parent)
    write_json(out_json, {"count": len(connections), "data": connections})
    print(f"Fetched data connections: {len(connections)} -> {out_json}")


if __name__ == "__main__":
    asyncio.run(_run())
