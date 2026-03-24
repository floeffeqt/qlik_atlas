from __future__ import annotations

import io
import json
import logging
import zipfile
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Customer, Project
from shared.qlik_client import QlikClient, QlikApiError
from .schemas import ThemeBuildRequest, ThemeUploadRequest, slugify_theme_name

logger = logging.getLogger("atlas.themes")


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


async def upload_theme_to_qlik(
    payload: ThemeUploadRequest,
    *,
    session: AsyncSession,
    actor_user_id: int,
    actor_role: str,
) -> dict[str, Any]:
    """Build theme ZIP and upload it to the project's Qlik Cloud tenant."""
    from ..database import apply_rls_context

    await apply_rls_context(session, actor_user_id, actor_role)

    proj_result = await session.execute(
        select(Project).where(Project.id == payload.project_id)
    )
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise ValueError(f"Project {payload.project_id} not found or not accessible")

    cust_result = await session.execute(
        select(Customer).where(Customer.id == project.customer_id)
    )
    customer = cust_result.scalar_one_or_none()
    if customer is None:
        raise ValueError("Customer for project not found")

    tenant_url = customer.tenant_url
    api_key = customer.api_key
    if not tenant_url or not api_key:
        raise ValueError("Customer credentials incomplete (tenant_url or api_key missing)")

    build_req = ThemeBuildRequest(
        theme_name=payload.theme_name,
        file_basename=payload.file_basename,
        qext=payload.qext,
        theme_json=payload.theme_json,
    )
    bundle = build_theme_zip(build_req, generated_by_user_id=str(actor_user_id))

    client = QlikClient(base_url=tenant_url, api_key=api_key, timeout=60.0)
    try:
        result, status_code = await client.post_file(
            "/api/v1/themes",
            file_content=bundle.content,
            file_name=bundle.filename,
        )
        logger.info("Theme uploaded to %s -> status=%s", tenant_url, status_code)
        theme_id = None
        if isinstance(result, dict):
            theme_id = result.get("id") or result.get("resourceId")
        return {"status": "uploaded", "detail": f"Theme uploaded to {tenant_url}", "theme_id": theme_id}
    except QlikApiError as exc:
        logger.error("Theme upload failed: %s (status=%s)", exc, exc.status_code)
        raise
    finally:
        await client.close()
