from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from ..auth.utils import get_current_user
from .schemas import ThemeBuildRequest, ThemeUploadStubRequest, ThemeUploadStubResponse
from .service import build_theme_zip


router = APIRouter(prefix="/themes", tags=["themes"])


@router.post("/build")
async def build_theme_bundle(
    payload: ThemeBuildRequest,
    current_user: dict = Depends(get_current_user),
) -> Response:
    bundle = build_theme_zip(payload, generated_by_user_id=str(current_user["user_id"]))
    headers = {
        "Content-Disposition": f'attachment; filename="{bundle.filename}"',
        "Cache-Control": "no-store",
    }
    return Response(content=bundle.content, media_type="application/zip", headers=headers)


@router.post("/upload", response_model=ThemeUploadStubResponse, status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def upload_theme_stub(
    payload: ThemeUploadStubRequest,
    _current_user: dict = Depends(get_current_user),
) -> ThemeUploadStubResponse:
    _ = payload
    return ThemeUploadStubResponse(
        status="not_implemented",
        detail="Theme upload is not implemented yet. Use /api/themes/build to download a ZIP bundle.",
    )

