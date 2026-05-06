"""
Database seeding script: creates initial admin user
Run after migrations: python -m scripts.seed_db
"""
import asyncio
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal
from app.models import User
from app.auth.utils import hash_password
from sqlalchemy import select, text


async def seed_db():
    """Seed admin user after Alembic migrations have created the schema."""
    print("Checking migration-managed schema...")
    async with AsyncSessionLocal() as session:
        alembic_version_exists = await session.execute(
            text("SELECT to_regclass('public.alembic_version')")
        )
        users_table_exists = await session.execute(
            text("SELECT to_regclass('public.users')")
        )
        if alembic_version_exists.scalar() is None:
            raise RuntimeError(
                "alembic_version table is missing. Run 'alembic upgrade head' before seeding."
            )
        if users_table_exists.scalar() is None:
            raise RuntimeError(
                "users table is missing. Migrations did not complete successfully."
            )

    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        raise RuntimeError(
            "ADMIN_EMAIL and ADMIN_PASSWORD must be set in environment variables."
        )

    print("Seeding admin user...")
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == admin_email))
        existing = result.scalar_one_or_none()

        if existing:
            if existing.role != "admin":
                existing.role = "admin"
                await session.commit()
                print("Upgraded existing user to admin")
            else:
                print("Admin user already exists")
        else:
            user = User(
                email=admin_email,
                password_hash=hash_password(admin_password),
                is_active=True,
                role="admin",
            )
            session.add(user)
            await session.commit()
            print(f"Admin user created: {admin_email}")

    print("Database seeding complete!")


if __name__ == "__main__":
    asyncio.run(seed_db())
