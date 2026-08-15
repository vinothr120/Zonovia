"""Local-only dev convenience: builds a file-based SQLite database (via Base.metadata.create_all,
not Alembic — the hand-written migrations use Postgres-specific SQL for RLS/JSONB/gen_random_uuid
and don't run against SQLite) and seeds it, so a frontend has something real to talk to without
needing Docker + Postgres locally.

THIS IS NOT THE PRODUCTION PATH. Production is always docker compose + Postgres + Alembic + Row-
Level Security, per docs/multi-tenancy.md. This script exists only for local development
convenience — RLS itself can't be exercised this way, see backend/tests/test_tenant_isolation.py
vs. test_tenant_isolation_postgres.py.

Usage (from backend/):
    python scripts/run_dev_sqlite.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")
os.environ.setdefault("JWT_SECRET_KEY", "dev-only-secret-not-for-production")
os.environ.setdefault("ENVIRONMENT", "development")


async def main() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.models_all import Base

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("SQLite schema created at ./dev.db")

    from app.seed import main as seed_main

    await seed_main()


if __name__ == "__main__":
    asyncio.run(main())
