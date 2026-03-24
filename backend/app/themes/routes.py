from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from ..auth.utils import get_current_user
from ..database import get_session
from .schemas import ThemeBuildRequest, ThemeUploadRequest, ThemeUploadResponse
from .service import build_theme_zip, upload_theme_to_qlik

logger = logging.getLogger("atlas.themes")

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


@router.post("/upload", response_model=ThemeUploadResponse)
async def upload_theme(
    payload: ThemeUploadRequest,
    current_user: dict = Depends(get_current_user),
    session=Depends(get_session),
) -> ThemeUploadResponse:
    try:
        result = await upload_theme_to_qlik(
            payload,
            session=session,
            actor_user_id=current_user["user_id"],
            actor_role=current_user.get("role", "user"),
        )
        return ThemeUploadResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Theme upload failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upload to Qlik failed: {exc}",
        ) from exc
