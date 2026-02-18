import os
from pathlib import Path
from typing import Any, Dict, List

from fetchers.fetch_usage import fetch_usage
from shared.utils import ensure_dir, read_json


DEFAULT_APPS_JSON = Path("../output/apps_inventory.json")
DEFAULT_OUTDIR = Path("../output/appusage")


def _load_apps(path: Path) -> List[Dict[str, Any]]:
    payload = read_json(path)
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        apps = payload.get("apps")
        if isinstance(apps, list):
            return [x for x in apps if isinstance(x, dict)]
    raise RuntimeError(f"Invalid apps source format: {path}")


def _clear_usage_artifacts(directory: Path) -> int:
    if not directory.exists() or not directory.is_dir():
        return 0
    removed = 0
    for path in directory.glob("*.json"):
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
    return removed


def _run() -> None:
    apps_path = Path(os.getenv("APPS_SOURCE_JSON", str(DEFAULT_APPS_JSON)))
    outdir = Path(os.getenv("APP_USAGE_OUTDIR", str(DEFAULT_OUTDIR)))
    window_days_raw = os.getenv("QLIK_USAGE_WINDOW_DAYS", "").strip()
    window_days = int(window_days_raw) if window_days_raw else None
    concurrency_raw = os.getenv("QLIK_USAGE_CONCURRENCY", "").strip()
    concurrency = int(concurrency_raw) if concurrency_raw else None

    apps = _load_apps(apps_path)
    if not apps:
        print(f"No apps found in {apps_path}")
        return

    ensure_dir(outdir)
    _clear_usage_artifacts(outdir)
    fetch_usage(
        apps=apps,
        window_days=window_days,
        outdir=outdir,
        concurrency=concurrency,
    )
    print(f"Fetched usage for apps: {len(apps)} -> {outdir}")


if __name__ == "__main__":
    _run()
