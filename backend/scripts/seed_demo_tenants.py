"""Demo-only mock data: a few additional tenants beyond app/seed.py's single "Acme
Corporation" (which stays the minimal, exact-numbers walkthrough tenant documented in the
README — untouched here), so a client demo can show off multi-tenancy with more than one
tenant to switch between. Phase 0 has no domain data beyond tenants/users/roles, so this is
intentionally small — it grows the same way app/seed.py does as Asset Core (Phase 1) and
later modules land. Safe to re-run — every step checks for an existing row before creating
one, same pattern as app/seed.py.

Usage (from backend/, with DATABASE_URL/DATABASE_URL_SYNC already exported — see .env.example):
    python -m scripts.seed_demo_tenants
"""

import asyncio

from sqlalchemy import select

from app.core.bootstrap import register_all_modules
from app.core.database import AsyncSessionLocal, set_tenant_session_var
from app.models_all import Base  # noqa: F401 — see app/seed.py's note on why this import matters.
from app.tenants.models import Tenant
from app.tenants.repository import TenantRepository
from app.users.models import Role
from app.users.repository import UserRepository
from app.users.service import UserService

SEED_PASSWORD = "ChangeMe123!"

DEMO_TENANTS = [
    {"slug": "northwind-logistics", "name": "Northwind Logistics", "tier": "basic"},
    {"slug": "riverside-hospital", "name": "Riverside Hospital Group", "tier": "professional"},
    {"slug": "lakeside-academy", "name": "Lakeside Academy", "tier": "basic"},
]

DEMO_ROLES = ["Tenant Admin", "Member", "Viewer"]


async def get_system_roles(db) -> dict[str, Role]:
    result = await db.execute(select(Role).where(Role.tenant_id.is_(None)))
    return {role.name: role for role in result.scalars().all()}


async def ensure_user(db, tenant_id, *, email: str, role: Role):
    user_repo = UserRepository(db, tenant_id)
    user = await user_repo.get_by_email(email)
    service = UserService(db, tenant_id)
    if user is None:
        user = await service.create_user(email=email, phone=None, password=SEED_PASSWORD, actor_user_id=None)

    assignments = await service.user_roles.list_for_user(user.id)
    if not any(a.role_id == role.id for a in assignments):
        await service.assign_role(
            user_id=user.id, role_id=role.id, scope_type="tenant", scope_id=None,
            actor_user_id=None, actor_is_platform_admin=True,
        )
    return user


async def seed_tenant(db, roles_by_name: dict[str, Role], profile: dict) -> None:
    slug = profile["slug"]
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_subdomain(slug)
    if tenant is None:
        tenant = tenant_repo.add(Tenant(name=profile["name"], subdomain=slug, subscription_tier=profile["tier"]))
        await db.flush()
    await set_tenant_session_var(db, tenant.id, local=False)

    for role_name in DEMO_ROLES:
        email = f"{role_name.lower().replace(' ', '')}@{slug}.example"
        await ensure_user(db, tenant.id, email=email, role=roles_by_name[role_name])
    await db.commit()

    print(f"  {profile['name']} (tenant_slug='{slug}'):")
    for role_name in DEMO_ROLES:
        email = f"{role_name.lower().replace(' ', '')}@{slug}.example"
        print(f"    {email} / {SEED_PASSWORD}  ({role_name})")


async def main() -> None:
    register_all_modules()

    async with AsyncSessionLocal() as db:
        roles_by_name = await get_system_roles(db)

    print(f"Seeding {len(DEMO_TENANTS)} additional demo tenants...\n")
    for profile in DEMO_TENANTS:
        async with AsyncSessionLocal() as db:
            await seed_tenant(db, roles_by_name, profile)

    print("\nDemo tenants seeded.")


if __name__ == "__main__":
    asyncio.run(main())
