"""
Database seeding script: creates initial admin user
Run after migrations: python -m scripts.seed_db
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal, engine, Base
from app.models import User
from app.auth.utils import hash_password
from sqlalchemy import select


async def seed_db():
    """Create tables and seed admin user"""
    print("Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("Seeding admin user...")
    async with AsyncSessionLocal() as session:
        # Check if user exists
        result = await session.execute(select(User).where(User.email == "admin@admin.de"))
        existing = result.scalar_one_or_none()

        if existing:
            if existing.role != "admin":
                existing.role = "admin"
                await session.commit()
                print("Upgraded existing user to admin")
            else:
                print("Admin user already exists")
        else:
            test_user = User(
                email="admin@admin.de",
                password_hash=hash_password("admin123"),
                is_active=True,
                role="admin",
            )
            session.add(test_user)
            await session.commit()
            print("Admin user created: admin@admin.de / admin123")

    print("Database seeding complete!")


if __name__ == "__main__":
    asyncio.run(seed_db())
