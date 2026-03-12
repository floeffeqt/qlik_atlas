import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.auth.utils import (  # type: ignore
    AUTH_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    hash_password,
)
from app.auth.rate_limit import LOGIN_RATE_LIMITER  # type: ignore
from app.database import Base, get_session  # type: ignore
from app.models import RefreshToken, User  # type: ignore
from main import app  # type: ignore


LEGACY_PBKDF2 = CryptContext(schemes=["pbkdf2_sha256"])


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_login_rate_limiter():
    previous = (
        LOGIN_RATE_LIMITER.ip_limit,
        LOGIN_RATE_LIMITER.email_limit,
        LOGIN_RATE_LIMITER.window_seconds,
        LOGIN_RATE_LIMITER.lockout_seconds,
    )
    LOGIN_RATE_LIMITER.reset()
    yield
    (
        LOGIN_RATE_LIMITER.ip_limit,
        LOGIN_RATE_LIMITER.email_limit,
        LOGIN_RATE_LIMITER.window_seconds,
        LOGIN_RATE_LIMITER.lockout_seconds,
    ) = previous
    LOGIN_RATE_LIMITER.reset()


@pytest.fixture(scope="session")
async def engine():
    url = "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine):
    return async_sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
async def db_session(session_factory):
    async def _get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    try:
        yield session_factory
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/health")
        assert r.status_code == 200
        payload = r.json()
        assert payload.get("status") == "ok"


@pytest.mark.asyncio
async def test_login_sets_access_and_refresh_cookie_and_me_uses_access_cookie(db_session):
    session_factory = db_session
    async with session_factory() as session:
        session.add(
            User(
                email="tester@example.com",
                password_hash=hash_password("secret123"),
                role="user",
                is_active=True,
            )
        )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        login = await ac.post("/api/auth/login", json={"email": "tester@example.com", "password": "secret123"})
        assert login.status_code == 200, login.text
        payload = login.json()
        assert payload["token_type"] == "cookie"
        assert payload["user"]["email"] == "tester@example.com"
        set_cookie = login.headers.get_list("set-cookie")
        assert any(AUTH_COOKIE_NAME in item for item in set_cookie)
        assert any(REFRESH_COOKIE_NAME in item for item in set_cookie)

        me = await ac.get("/api/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["email"] == "tester@example.com"

        async with session_factory() as session:
            rows = (await session.execute(select(RefreshToken))).scalars().all()
            assert len(rows) == 1
            assert rows[0].revoked_at is None


@pytest.mark.asyncio
async def test_refresh_rotates_refresh_token_and_keeps_session_alive(db_session):
    session_factory = db_session
    async with session_factory() as session:
        session.add(
            User(
                email="rotate@example.com",
                password_hash=hash_password("secret123"),
                role="admin",
                is_active=True,
            )
        )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        login = await ac.post("/api/auth/login", json={"email": "rotate@example.com", "password": "secret123"})
        assert login.status_code == 200, login.text

        refresh = await ac.post("/api/auth/refresh")
        assert refresh.status_code == 200, refresh.text
        payload = refresh.json()
        assert payload["user"]["email"] == "rotate@example.com"
        set_cookie = refresh.headers.get_list("set-cookie")
        assert any(AUTH_COOKIE_NAME in item for item in set_cookie)
        assert any(REFRESH_COOKIE_NAME in item for item in set_cookie)

        me = await ac.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == "rotate@example.com"

        async with session_factory() as session:
            rows = (await session.execute(select(RefreshToken).order_by(RefreshToken.token_id))).scalars().all()
            assert len(rows) == 2
            assert rows[0].revoked_at is not None
            assert rows[0].replaced_by_token_id == rows[1].token_id
            assert rows[1].revoked_at is None


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token_and_clears_follow_up_access(db_session):
    session_factory = db_session
    async with session_factory() as session:
        session.add(
            User(
                email="logout@example.com",
                password_hash=hash_password("secret123"),
                role="admin",
                is_active=True,
            )
        )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        login = await ac.post("/api/auth/login", json={"email": "logout@example.com", "password": "secret123"})
        assert login.status_code == 200, login.text

        logout = await ac.post("/api/auth/logout")
        assert logout.status_code == 200, logout.text
        assert logout.json() == {"ok": True}
        set_cookie = logout.headers.get_list("set-cookie")
        assert any(AUTH_COOKIE_NAME in item and "Max-Age=0" in item for item in set_cookie)
        assert any(REFRESH_COOKIE_NAME in item and "Max-Age=0" in item for item in set_cookie)

        me = await ac.get("/api/auth/me")
        assert me.status_code == 401

        async with session_factory() as session:
            rows = (await session.execute(select(RefreshToken))).scalars().all()
            assert len(rows) == 1
            assert rows[0].revoked_at is not None


@pytest.mark.asyncio
async def test_login_rate_limit_blocks_after_repeated_ip_failures(db_session):
    LOGIN_RATE_LIMITER.ip_limit = 3
    LOGIN_RATE_LIMITER.email_limit = 10
    LOGIN_RATE_LIMITER.window_seconds = 3600
    LOGIN_RATE_LIMITER.lockout_seconds = 120

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for idx in range(2):
            res = await ac.post(
                "/api/auth/login",
                json={"email": f"missing-{idx}@example.com", "password": "wrong"},
                headers={"x-forwarded-for": "203.0.113.10"},
            )
            assert res.status_code == 401

        blocked = await ac.post(
            "/api/auth/login",
            json={"email": "missing-3@example.com", "password": "wrong"},
            headers={"x-forwarded-for": "203.0.113.10"},
        )
        assert blocked.status_code == 429
        assert blocked.headers.get("retry-after") == "120"


@pytest.mark.asyncio
async def test_login_rate_limit_blocks_after_repeated_email_failures_across_ips(db_session):
    session_factory = db_session
    async with session_factory() as session:
        session.add(
            User(
                email="ratelimit@example.com",
                password_hash=hash_password("secret123"),
                role="user",
                is_active=True,
            )
        )
        await session.commit()

    LOGIN_RATE_LIMITER.ip_limit = 10
    LOGIN_RATE_LIMITER.email_limit = 2
    LOGIN_RATE_LIMITER.window_seconds = 3600
    LOGIN_RATE_LIMITER.lockout_seconds = 90

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        first = await ac.post(
            "/api/auth/login",
            json={"email": "ratelimit@example.com", "password": "wrong"},
            headers={"x-forwarded-for": "198.51.100.11"},
        )
        assert first.status_code == 401

        blocked = await ac.post(
            "/api/auth/login",
            json={"email": "ratelimit@example.com", "password": "wrong"},
            headers={"x-forwarded-for": "198.51.100.12"},
        )
        assert blocked.status_code == 429
        assert blocked.headers.get("retry-after") == "90"


@pytest.mark.asyncio
async def test_login_rehashes_legacy_pbkdf2_password_hash_to_argon2(db_session):
    session_factory = db_session
    async with session_factory() as session:
        session.add(
            User(
                email="legacy@example.com",
                password_hash=LEGACY_PBKDF2.hash("secret123"),
                role="user",
                is_active=True,
            )
        )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        login = await ac.post("/api/auth/login", json={"email": "legacy@example.com", "password": "secret123"})
        assert login.status_code == 200, login.text

    async with session_factory() as session:
        user = (await session.execute(select(User).where(User.email == "legacy@example.com"))).scalar_one()
        assert user.password_hash.startswith("$argon2id$")
