import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from ..database import get_session
from ..models import QlikCredential
from ..auth.utils import get_current_user_id

router = APIRouter(prefix="/settings", tags=["settings"])


class QlikCredentialIn(BaseModel):
    tenant_url: str
    api_key: str


class QlikCredentialOut(BaseModel):
    tenant_url: str
    api_key_set: bool
    api_key_preview: str


@router.get("/qlik", response_model=QlikCredentialOut)
async def get_qlik_settings(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_user_id),
):
    result = await session.execute(select(QlikCredential).limit(1))
    cred = result.scalar_one_or_none()
    if not cred:
        return QlikCredentialOut(tenant_url="", api_key_set=False, api_key_preview="")
    preview = ("••••••••" + cred.api_key[-4:]) if len(cred.api_key) > 4 else "••••"
    return QlikCredentialOut(tenant_url=cred.tenant_url, api_key_set=True, api_key_preview=preview)


@router.put("/qlik")
async def save_qlik_settings(
    payload: QlikCredentialIn,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_user_id),
):
    if not payload.tenant_url.strip():
        raise HTTPException(status_code=400, detail="tenant_url must not be empty")
    if not payload.api_key.strip():
        raise HTTPException(status_code=400, detail="api_key must not be empty")

    tenant_url = payload.tenant_url.strip().rstrip("/")
    api_key = payload.api_key.strip()

    result = await session.execute(select(QlikCredential).limit(1))
    cred = result.scalar_one_or_none()
    if cred:
        cred.tenant_url = tenant_url
        cred.api_key = api_key
    else:
        cred = QlikCredential(tenant_url=tenant_url, api_key=api_key)
        session.add(cred)
    await session.commit()

    # Push into process environment so existing fetch logic picks them up immediately
    os.environ["QLIK_TENANT_URL"] = tenant_url
    os.environ["QLIK_API_KEY"] = api_key

    return {"status": "ok", "tenant_url": tenant_url}
