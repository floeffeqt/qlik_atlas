import json
import re
import csv
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    from openpyxl import Workbook
except Exception:  # pragma: no cover - optional dependency
    Workbook = None


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def sanitize_name(name: str, max_len: int = 120) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip())
    safe = safe[:max_len]
    return safe or "app"


def url_encode_qri(qri: str) -> str:
    return quote(qri, safe="")


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_csv(path: Path, rows: Any, headers: Any) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(headers))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_xlsx(path: Path, rows: Any, headers: Any) -> None:
    if Workbook is None:
        raise RuntimeError("openpyxl is not installed")
    ensure_dir(path.parent)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "apps"
    sheet.append(list(headers))
    for row in rows:
        sheet.append([row.get(h, "") for h in headers])
    workbook.save(path)
