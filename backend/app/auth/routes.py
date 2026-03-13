import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import RefreshToken, User
from ..serialization import iso_or_empty
from .rate_limit import LOGIN_RATE_LIMITER, normalize_login_email
from .schemas import AdminUserCreate, AuthSessionResponse, LogoutResponse, UserCreate, UserOut
from .utils import (
    clear_access_cookie,
    clear_refresh_cookie,
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_refresh_cookie_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    refresh_token_hashes,
    require_admin,
    set_access_cookie,
    set_refresh_cookie,
    verify_password_and_rehash,
)

router = APIRouter(prefix="/auth", tags=["auth"])
auth_logger = logging.getLogger("uvicorn.error")


def _serialize_user(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=iso_or_empty(user.created_at),
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _client_ip(request: Request | None) -> str:
    if request is None:
        return "unknown"
    forwarded_for = (request.headers.get("x-forwarded-for", "") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or "unknown"
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


def _raise_login_rate_limited(retry_after_seconds: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many login attempts. Please retry later.",
        headers={"Retry-After": str(max(1, retry_after_seconds))},
    )


def _log_login_event(
    *,
    event: str,
    email: str,
    ip_address: str,
    user_id: int | None = None,
    outcome: str,
    retry_after_seconds: int | None = None,
    scope: str | None = None,
) -> None:
    auth_logger.info(
        "auth_login_event event=%s outcome=%s email=%s ip=%s user_id=%s scope=%s retry_after=%s",
        event,
        outcome,
        normalize_login_email(email),
        ip_address,
        user_id if user_id is not None else "-",
        scope or "-",
        retry_after_seconds if retry_after_seconds is not None else "-",
    )


async def _issue_refresh_token(session: AsyncSession, user_id: int) -> tuple[str, RefreshToken]:
    refresh_plain = create_refresh_token()
    refresh_row = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(refresh_plain),
        expires_at=refresh_token_expiry(),
    )
    session.add(refresh_row)
    await session.flush()
    return refresh_plain, refresh_row


def _set_session_cookies(response: Response, user: User, refresh_plain: str) -> None:
    access_token = create_access_token(str(user.id), role=user.role, email=user.email)
    set_access_cookie(response, access_token)
    set_refresh_cookie(response, refresh_plain)


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
    return _serialize_user(user)


@router.post("/login", response_model=AuthSessionResponse)
async def login(
    payload: UserCreate,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    client_ip = _client_ip(request)
    email_key = normalize_login_email(payload.email)
    status_check = LOGIN_RATE_LIMITER.check(client_ip, email_key)
    if status_check.blocked:
        _log_login_event(
            event="blocked",
            email=email_key,
            ip_address=client_ip,
            outcome="rate_limited",
            retry_after_seconds=status_check.retry_after_seconds,
            scope=status_check.scope,
        )
        _raise_login_rate_limited(status_check.retry_after_seconds)

    q = await session.execute(select(User).where(User.email == payload.email))
    user = q.scalar_one_or_none()
    password_valid = False
    upgraded_password_hash: str | None = None
    if user:
        password_valid, upgraded_password_hash = verify_password_and_rehash(payload.password, user.password_hash)
    if not user or not password_valid:
        blocked = LOGIN_RATE_LIMITER.register_failure(client_ip, email_key)
        _log_login_event(
            event="failed",
            email=email_key,
            ip_address=client_ip,
            outcome="invalid_credentials",
            scope=blocked.scope,
            retry_after_seconds=blocked.retry_after_seconds if blocked.blocked else None,
        )
        if blocked.blocked:
            _raise_login_rate_limited(blocked.retry_after_seconds)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        blocked = LOGIN_RATE_LIMITER.register_failure(client_ip, email_key)
        _log_login_event(
            event="failed",
            email=email_key,
            ip_address=client_ip,
            user_id=user.id,
            outcome="account_deactivated",
            scope=blocked.scope,
            retry_after_seconds=blocked.retry_after_seconds if blocked.blocked else None,
        )
        if blocked.blocked:
            _raise_login_rate_limited(blocked.retry_after_seconds)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")

    LOGIN_RATE_LIMITER.register_success(client_ip, email_key)
    if upgraded_password_hash:
        user.password_hash = upgraded_password_hash
    refresh_plain, _refresh_row = await _issue_refresh_token(session, user.id)
    await session.commit()
    _set_session_cookies(response, user, refresh_plain)
    _log_login_event(
        event="success",
        email=email_key,
        ip_address=client_ip,
        user_id=user.id,
        outcome="login_ok",
    )
    return AuthSessionResponse(token_type="cookie", user=_serialize_user(user))


@router.post("/refresh", response_model=AuthSessionResponse)
async def refresh_session(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    refresh_plain = get_refresh_cookie_token(request)
    if not refresh_plain:
        clear_access_cookie(response)
        clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")

    q = await session.execute(select(RefreshToken).where(RefreshToken.token_hash.in_(refresh_token_hashes(refresh_plain))))
    stored = q.scalar_one_or_none()
    now = _utc_now()
    if not stored or stored.revoked_at is not None or stored.expires_at <= now:
        clear_access_cookie(response)
        clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    user_query = await session.execute(select(User).where(User.id == stored.user_id))
    user = user_query.scalar_one_or_none()
    if not user:
        stored.revoked_at = now
        stored.last_used_at = now
        await session.commit()
        clear_access_cookie(response)
        clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if not user.is_active:
        stored.revoked_at = now
        stored.last_used_at = now
        await session.commit()
        clear_access_cookie(response)
        clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")

    stored.revoked_at = now
    stored.last_used_at = now
    next_refresh_plain, next_refresh_row = await _issue_refresh_token(session, user.id)
    stored.replaced_by_token_id = next_refresh_row.token_id
    await session.commit()
    _set_session_cookies(response, user, next_refresh_plain)
    return AuthSessionResponse(token_type="cookie", user=_serialize_user(user))


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    refresh_plain = get_refresh_cookie_token(request)
    if refresh_plain:
        q = await session.execute(select(RefreshToken).where(RefreshToken.token_hash.in_(refresh_token_hashes(refresh_plain))))
        stored = q.scalar_one_or_none()
        if stored and stored.revoked_at is None:
            stored.revoked_at = _utc_now()
            stored.last_used_at = _utc_now()
            await session.commit()
    clear_access_cookie(response)
    clear_refresh_cookie(response)
    return LogoutResponse(ok=True)


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
    return _serialize_user(user)
