from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from typing import Any

from .schemas import ThemeBuildRequest, slugify_theme_name


@dataclass(frozen=True)
class ThemeZipBundle:
    filename: str
    content: bytes


def _build_qext(payload: ThemeBuildRequest, *, generated_by_user_id: str) -> dict[str, Any]:
    _ = generated_by_user_id
    qext = payload.qext
    data: dict[str, Any] = {
        "name": qext.name or payload.theme_name,
        "type": "theme",
        "version": qext.version or "1.0.0",
    }
    if qext.description:
        data["description"] = qext.description
    if qext.author:
        data["author"] = qext.author
    if qext.homepage:
        data["homepage"] = qext.homepage
    if qext.icon:
        data["icon"] = qext.icon
    if qext.preview:
        data["preview"] = qext.preview
    if qext.keywords:
        data["keywords"] = qext.keywords
    return data


def build_theme_zip(payload: ThemeBuildRequest, *, generated_by_user_id: str) -> ThemeZipBundle:
    theme_id = payload.file_basename or slugify_theme_name(payload.theme_name)
    qext_json = json.dumps(_build_qext(payload, generated_by_user_id=generated_by_user_id), indent=2, sort_keys=True)
    theme_json = json.dumps(payload.theme_json, indent=2, sort_keys=True)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("theme.json", theme_json + "\n")
        zf.writestr(f"{theme_id}.qext", qext_json + "\n")

    filename = f"{theme_id}.zip"
    return ThemeZipBundle(filename=filename, content=buffer.getvalue())
