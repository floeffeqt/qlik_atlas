from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://atlas:atlas@db:5432/atlas_db")

engine = create_async_engine(DATABASE_URL, echo=False, future=True, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_session():
    async with AsyncSessionLocal() as session:
        yield session


async def apply_rls_context(session: AsyncSession, user_id: str | int, role: str) -> None:
    """Set per-transaction PostgreSQL session settings used by RLS policies."""
    await session.execute(
        text(
            "SELECT "
            "set_config('app.user_id', :user_id, true), "
            "set_config('app.role', :role, true)"
        ),
        {"user_id": str(user_id), "role": str(role)},
    )
