"""
One-time migration helper: reads JSON artifacts and imports into the database.
This script is intentionally a dry-run helper and will not run automatically.
Run manually after configuring DATABASE_URL and ensuring the DB is reachable.
"""
import asyncio
import json
from pathlib import Path
import os

from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal, engine


async def migrate():
    # Example placeholder: implement per-project mappings
    print('Scanning output directory for JSON files...')
    base = Path(__file__).resolve().parents[2]
    out = base / 'output'
    files = list(out.rglob('*.json'))
    print(f'Found {len(files)} json files')

    async with AsyncSessionLocal() as session:  # type: ignore
        # TODO: implement mapping from JSON -> DB tables
        for p in files:
            print('Would migrate', p)


if __name__ == '__main__':
    asyncio.run(migrate())
