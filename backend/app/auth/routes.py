from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_session
from ..models import User
from .schemas import UserCreate, AdminUserCreate, Token, UserOut
from .utils import hash_password, verify_password, create_access_token, get_current_user, require_admin

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    payload: AdminUserCreate,
    session: AsyncSession = Depends(get_session),
    _admin: dict = Depends(require_admin),
):
    """Create a new user (admin only)."""
    q = await session.execute(select(User).where(User.email == payload.email))
    existing = q.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


@router.post("/login", response_model=Token)
async def login(payload: UserCreate, session: AsyncSession = Depends(get_session)):
    q = await session.execute(select(User).where(User.email == payload.email))
    user = q.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")
    token = create_access_token(str(user.id), role=user.role, email=user.email)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
async def get_me(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Return the current user's profile."""
    q = await session.execute(select(User).where(User.id == int(current_user["user_id"])))
    user = q.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )
