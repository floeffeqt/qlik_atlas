import os
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from jose import jwt, JWTError

from ..database import get_session
from ..models import User
from shared.config import is_prod

pwd_context = CryptContext(
    schemes=["argon2", "pbkdf2_sha256"],
    default="argon2",
    deprecated=["pbkdf2_sha256"],
)
JWT_SECRET = os.getenv("JWT_SECRET", "replace_this_with_secure_value_in_production")
REFRESH_TOKEN_HMAC_KEY = (os.getenv("REFRESH_TOKEN_HMAC_KEY", "") or JWT_SECRET)
ALGORITHM = "HS256"
ACCESS_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
AUTH_COOKIE_NAME = (os.getenv("AUTH_COOKIE_NAME", "atlas_access_token") or "atlas_access_token").strip()
AUTH_COOKIE_SECURE = (os.getenv("AUTH_COOKIE_SECURE", "1" if is_prod() else "0") or "0").strip().lower() in ("1", "true", "yes", "on")
AUTH_COOKIE_DOMAIN = (os.getenv("AUTH_COOKIE_DOMAIN", "") or "").strip() or None
AUTH_COOKIE_PATH = (os.getenv("AUTH_COOKIE_PATH", "/") or "/").strip() or "/"
AUTH_COOKIE_SAMESITE = (os.getenv("AUTH_COOKIE_SAMESITE", "lax") or "lax").strip().lower()
REFRESH_COOKIE_NAME = (os.getenv("REFRESH_COOKIE_NAME", "atlas_refresh_token") or "atlas_refresh_token").strip()
REFRESH_COOKIE_PATH = (os.getenv("REFRESH_COOKIE_PATH", "/api/auth") or "/api/auth").strip() or "/api/auth"
if AUTH_COOKIE_SAMESITE not in ("lax", "strict", "none"):
    AUTH_COOKIE_SAMESITE = "lax"

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    valid, _updated_hash = verify_password_and_rehash(plain, hashed)
    return valid


def verify_password_and_rehash(plain: str, hashed: str) -> tuple[bool, str | None]:
    try:
        valid, updated_hash = pwd_context.verify_and_update(plain, hashed)
        return bool(valid), updated_hash
    except (ValueError, UnknownHashError):
        return False, None


def create_access_token(subject: str, role: str = "user", email: str = "") -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_EXPIRE_MINUTES)
    to_encode = {"exp": expire, "sub": str(subject), "role": role, "email": email}
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hmac.new(
        REFRESH_TOKEN_HMAC_KEY.encode(), token.encode(), hashlib.sha256
    ).hexdigest()


def _legacy_sha256(token: str) -> str:
    """Plain SHA256 used before HMAC migration. Remove after transition (REFRESH_EXPIRE_DAYS)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_hashes(token: str) -> list[str]:
    """Return [hmac_hash, legacy_sha256_hash] for transition-period DB lookups."""
    return [hash_refresh_token(token), _legacy_sha256(token)]


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRE_DAYS)


def set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=ACCESS_EXPIRE_MINUTES * 60,
        expires=ACCESS_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
        domain=AUTH_COOKIE_DOMAIN,
        path=AUTH_COOKIE_PATH,
    )


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=REFRESH_EXPIRE_DAYS * 24 * 60 * 60,
        expires=REFRESH_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
        domain=AUTH_COOKIE_DOMAIN,
        path=REFRESH_COOKIE_PATH,
    )


def clear_access_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        domain=AUTH_COOKIE_DOMAIN,
        path=AUTH_COOKIE_PATH,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
        httponly=True,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        domain=AUTH_COOKIE_DOMAIN,
        path=REFRESH_COOKIE_PATH,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
        httponly=True,
    )


def get_refresh_cookie_token(request: Request | None) -> str:
    if request is None:
        return ""
    return (request.cookies.get(REFRESH_COOKIE_NAME, "") or "").strip()


def _resolve_token(
    credentials: HTTPAuthorizationCredentials | None,
    request: Request | None,
) -> str | None:
    if credentials and credentials.credentials:
        return credentials.credentials
    if request is not None:
        cookie_token = (request.cookies.get(AUTH_COOKIE_NAME, "") or "").strip()
        if cookie_token:
            return cookie_token
    return None


async def get_current_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    token = _resolve_token(credentials, request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Returns {"user_id": str, "role": str} with DB-revalidated role/is_active."""
    token = _resolve_token(credentials, request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id_claim: str | None = payload.get("sub")
        if not user_id_claim:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        try:
            user_id = int(str(user_id_claim))
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        q = await session.execute(select(User).where(User.id == user_id))
        user = q.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")
        return {"user_id": str(user.id), "role": str(user.role or "user")}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Raises 403 if the authenticated user is not an admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
