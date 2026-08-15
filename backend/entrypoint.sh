#!/bin/sh
set -e

echo "Waiting for database..."
python - <<'PYEOF'
import asyncio
import os
import sys
import time

import asyncpg


async def wait() -> None:
    dsn = os.environ["DATABASE_URL_SYNC"].replace("postgresql+psycopg2", "postgresql")
    for attempt in range(30):
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            return
        except Exception:
            time.sleep(1)
    sys.exit("Database not reachable after 30s")


asyncio.run(wait())
PYEOF

echo "Running migrations..."
alembic upgrade head

if [ "$ENVIRONMENT" = "development" ]; then
    echo "Seeding development data..."
    python -m app.seed || true
fi

echo "Starting server with ${WEB_CONCURRENCY:-1} worker(s)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-1}"
