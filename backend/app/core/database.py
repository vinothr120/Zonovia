import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True, echo=False)

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


async def set_tenant_session_var(session: AsyncSession, tenant_id: uuid.UUID, *, local: bool = True) -> None:
    """Sets the Postgres session variable RLS policies check (`app.current_tenant_id`) via
    `set_config(...)` so isolation is enforced by the database itself, not just by the
    app-layer filtering in TenantScopedRepository — see docs/multi-tenancy.md for why both
    layers exist. `local=True` (SET LOCAL semantics) is correct for one request's transaction;
    seed/admin scripts that span multiple statements outside a single short transaction use
    `local=False`.

    A no-op against any non-Postgres engine (SQLite has no set_config) — this is what lets
    the exact same service code run in the SQLite-backed unit test tier (which validates the
    app-layer half of isolation) without every test needing a live Postgres connection.
    """
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    await session.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, :local)"),
        {"tid": str(tenant_id), "local": local},
    )
