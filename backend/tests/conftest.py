import os
import tempfile
import uuid

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
# Phase 1 — Asset Core's AssetDocument is the first real file-upload caller; route the
# LocalStorageBackend (app/core/storage.py) at a throwaway system temp dir for the test run
# rather than the default ./storage (which would otherwise litter the repo working tree).
os.environ.setdefault("FILE_STORAGE_ROOT", tempfile.mkdtemp(prefix="zonovia-test-storage-"))

import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.bootstrap import register_all_modules
from app.core.exceptions import AppError
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models_all import Base
from app.tenants.models import Tenant
from app.users.models import Permission, Role, RolePermission, User, UserRole

register_all_modules()


@pytest_asyncio.fixture
async def engine():
    """A fresh in-memory SQLite database per test — fast, and exercises the exact same
    SQLAlchemy models the app uses against Postgres. This tier validates the APPLICATION-
    LAYER half of tenant isolation (TenantScopedRepository's explicit tenant_id filtering).
    Postgres Row-Level Security itself is Postgres-only and is covered by the integration
    tests in test_tenant_isolation_postgres.py, which require `docker compose up -d postgres`."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(bind=engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(session_factory):
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(session_factory):
    async def override_get_db(payload: deps.TokenPayload = Depends(deps.get_token_payload)):  # noqa: ARG001
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except AppError:
                await session.commit()  # mirrors app/core/deps.py's get_db — see its comment
                raise
            except Exception:
                await session.rollback()
                raise

    async def override_get_public_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except AppError:
                await session.commit()
                raise
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[deps.get_db] = override_get_db
    app.dependency_overrides[deps.get_public_db] = override_get_public_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def make_tenant(db, *, subdomain: str) -> Tenant:
    tenant = Tenant(name=subdomain, subdomain=subdomain, subscription_tier="basic")
    db.add(tenant)
    await db.flush()
    return tenant


async def make_permission(db, key: str, module_key: str = "test") -> Permission:
    existing = (await db.execute(select(Permission).where(Permission.key == key))).scalar_one_or_none()
    if existing is not None:
        return existing
    perm = Permission(key=key, module_key=module_key, description=key)
    db.add(perm)
    await db.flush()
    return perm


async def make_role_with_permissions(db, *, tenant_id: uuid.UUID | None, name: str, permission_keys: list[str]) -> Role:
    role = Role(tenant_id=tenant_id, name=name, is_system_role=tenant_id is None)
    db.add(role)
    await db.flush()
    for key in permission_keys:
        perm = await make_permission(db, key)
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    await db.flush()
    return role


async def make_user_with_role(
    db, *, tenant_id: uuid.UUID, email: str, role: Role, scope_type: str = "tenant", scope_id=None
) -> tuple[User, str]:
    user = User(tenant_id=tenant_id, email=email, password_hash=hash_password("Passw0rd!2026"), status="active")
    db.add(user)
    await db.flush()
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id, scope_type=scope_type, scope_id=scope_id))
    await db.flush()
    token = create_access_token(user_id=user.id, tenant_id=tenant_id)
    return user, token
