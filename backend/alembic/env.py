import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import Base

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = os.getenv("DATABASE_URL", "postgresql+asyncpg://atlas:atlas@db:5432/atlas_db")
    # Use async engine for asyncpg URLs
    from sqlalchemy.ext.asyncio import create_async_engine

    async_engine = create_async_engine(configuration["sqlalchemy.url"], poolclass=pool.NullPool)

    def run_sync_migrations(sync_connection: Connection) -> None:
        context.configure(connection=sync_connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    import asyncio

    async def run_async():
        async with async_engine.connect() as conn:
            await conn.run_sync(run_sync_migrations)
        await async_engine.dispose()

    asyncio.run(run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
