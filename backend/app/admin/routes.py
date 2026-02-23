from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func
from ..database import get_session
from ..models import User
from ..auth.utils import require_admin
from ..auth.schemas import UserOut, UserUpdate

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=list[UserOut])
async def list_users(
    session: AsyncSession = Depends(get_session),
    _admin: dict = Depends(require_admin),
):
    result = await session.execute(select(User).order_by(User.email))
    users = result.scalars().all()
    return [
        UserOut(
            id=u.id,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at.isoformat() if u.created_at else "",
        )
        for u in users
    ]


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
    _admin: dict = Depends(require_admin),
):
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent demoting the last admin
    if payload.role is not None and payload.role != "admin" and user.role == "admin":
        count_result = await session.execute(
            select(sa_func.count()).select_from(User).where(User.role == "admin", User.is_active == True)
        )
        admin_count = count_result.scalar() or 0
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last active admin")

    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    await session.commit()
    await session.refresh(user)
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )
