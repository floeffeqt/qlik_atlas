import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.auth import utils as auth_utils  # type: ignore


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


@pytest.mark.asyncio
async def test_get_current_user_revalidates_role_from_db():
    token = auth_utils.create_access_token("7", role="admin", email="user@example.com")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db_user = SimpleNamespace(id=7, role="user", is_active=True)
    session = _FakeSession(db_user)

    current = await auth_utils.get_current_user(credentials=credentials, session=session)
    assert current["user_id"] == "7"
    assert current["role"] == "user"


@pytest.mark.asyncio
async def test_get_current_user_blocks_deactivated_user():
    token = auth_utils.create_access_token("9", role="admin", email="user@example.com")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db_user = SimpleNamespace(id=9, role="admin", is_active=False)
    session = _FakeSession(db_user)

    with pytest.raises(HTTPException) as exc:
        await auth_utils.get_current_user(credentials=credentials, session=session)
    assert exc.value.status_code == 403
    assert "deactivated" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_require_admin_rejects_non_admin_role():
    with pytest.raises(HTTPException) as exc:
        await auth_utils.require_admin(current_user={"user_id": "1", "role": "user"})
    assert exc.value.status_code == 403
