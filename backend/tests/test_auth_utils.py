import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from passlib.context import CryptContext
from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.auth import utils as auth_utils  # type: ignore


LEGACY_PBKDF2 = CryptContext(schemes=["pbkdf2_sha256"])


class _FakeResult:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class _FakeSession:
    def __init__(self, user):
        self._user = user

    async def execute(self, _stmt):
        return _FakeResult(self._user)


def _request():
    return Request(
        {
            "type": "http",
            "headers": [],
            "method": "GET",
            "path": "/api/test",
        }
    )


@pytest.mark.asyncio
async def test_get_current_user_revalidates_role_from_db():
    token = auth_utils.create_access_token("7", role="admin", email="user@example.com")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db_user = SimpleNamespace(id=7, role="user", is_active=True)
    session = _FakeSession(db_user)

    current = await auth_utils.get_current_user(request=_request(), credentials=credentials, session=session)
    assert current["user_id"] == "7"
    assert current["role"] == "user"


@pytest.mark.asyncio
async def test_get_current_user_blocks_deactivated_user():
    token = auth_utils.create_access_token("9", role="admin", email="user@example.com")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db_user = SimpleNamespace(id=9, role="admin", is_active=False)
    session = _FakeSession(db_user)

    with pytest.raises(HTTPException) as exc:
        await auth_utils.get_current_user(request=_request(), credentials=credentials, session=session)
    assert exc.value.status_code == 403
    assert "deactivated" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_require_admin_rejects_non_admin_role():
    with pytest.raises(HTTPException) as exc:
        await auth_utils.require_admin(current_user={"user_id": "1", "role": "user"})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_user_id_accepts_http_only_cookie_fallback():
    token = auth_utils.create_access_token("11", role="user", email="cookie@example.com")
    request = _request()
    request._cookies = {auth_utils.AUTH_COOKIE_NAME: token}

    current_user_id = await auth_utils.get_current_user_id(request=request, credentials=None)
    assert current_user_id == "11"


def test_hash_password_uses_argon2id_by_default():
    hashed = auth_utils.hash_password("secret123")
    assert hashed.startswith("$argon2id$")


def test_verify_password_and_rehash_upgrades_legacy_pbkdf2_hash():
    legacy_hash = LEGACY_PBKDF2.hash("secret123")
    valid, upgraded_hash = auth_utils.verify_password_and_rehash("secret123", legacy_hash)

    assert valid is True
    assert upgraded_hash is not None
    assert upgraded_hash.startswith("$argon2id$")
