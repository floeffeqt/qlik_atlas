import sys
from pathlib import Path
import pytest
from httpx import AsyncClient
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


# Ensure backend package is importable
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import Base, get_session  # type: ignore
from main import app  # type: ignore


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def engine():
    url = "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(engine):
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _get_session():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    try:
        yield
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
async def test_register_and_login(db_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        user = {"email": "tester@example.com", "password": "secret123"}

        # register
        r = await ac.post("/auth/register", json=user)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data

        # duplicate register fails
        r2 = await ac.post("/auth/register", json=user)
        assert r2.status_code == 400

        # login success
        r3 = await ac.post("/auth/login", json=user)
        assert r3.status_code == 200
        assert "access_token" in r3.json()

        # bad password fails
        r4 = await ac.post("/auth/login", json={"email": user["email"], "password": "bad"})
        assert r4.status_code == 401
