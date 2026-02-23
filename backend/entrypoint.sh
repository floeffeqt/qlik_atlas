#!/bin/bash
set -e

echo "⏳ Waiting for database..."
sleep 2

echo "🔄 Running migrations..."
cd /app
alembic upgrade head || true

echo "📝 Seeding database..."
python -m scripts.seed_db || true

echo "🚀 Starting application..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers
