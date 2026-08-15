"""Development seed data — creates the platform operator tenant + Platform Admin, and a demo
tenant with one user per Phase 0 role bundle. Safe to re-run: every step checks for an
existing row before creating one.

Usage (from backend/, with DATABASE_URL/DATABASE_URL_SYNC set — see .env.example):
    python -m app.seed
"""

import asyncio

from sqlalchemy import select

from app.core.bootstrap import register_all_modules
from app.core.database import AsyncSessionLocal, set_tenant_session_var
from app.core.module_registry import get_registered_modules
from app.models_all import Base  # noqa: F401 — registers every mapped model on Base.metadata

# before any relationship/FK is resolved. Without this, running this module directly
# (`python -m app.seed`, exactly what entrypoint.sh does) never imports a model module that
# nothing above imports directly, and a flush can blow up with NoReferencedTableError.
from app.tenants.models import Tenant
from app.tenants.repository import TenantRepository
from app.users.models import Permission, Role, RolePermission
from app.users.repository import PermissionRepository, UserRepository
from app.users.service import UserService

SEED_PASSWORD = "ChangeMe123!"

# None = every currently-registered permission (Platform Admin). Every other role gets
# exactly the permissions relevant to it — Phase 1+ modules add their own keys to
# "Tenant Admin"/"Member"/"Viewer" here as they register, per the implementation plan's
# naming decisions (these bundle names are asset-tracking-neutral so future modules extend
# them without a rename).
DEFAULT_ROLE_BUNDLES: dict[str, list[str] | None] = {
    "Platform Admin": None,
    "Tenant Admin": [
        "users.view",
        "users.create",
        "users.edit",
        "users.delete",
        "roles.view",
        "roles.manage",
        "audit_logs.view",
        "tenants.view_settings",
        "tenants.manage_settings",
        "entitlements.view",
        # Phase 1 — Asset Core: Tenant Admin gets everything, including
        # asset_lifecycle.configure (editing the tenant-wide state machine is reserved — a
        # bad edit breaks every future transition, so only Tenant Admin/Platform Admin get it).
        "assets.view",
        "assets.create",
        "assets.edit",
        "assets.delete",
        "assets.manage_documents",
        "asset_catalog.manage",
        "asset_locations.view",
        "asset_locations.manage",
        "asset_lifecycle.view",
        "assets.transition_lifecycle",
        "assets.assign",
        "assets.move",
        "asset_lifecycle.configure",
    ],
    "Member": [
        "users.view",
        # Phase 1 — Asset Core: Member gets everything except asset_lifecycle.configure.
        "assets.view",
        "assets.create",
        "assets.edit",
        "assets.delete",
        "assets.manage_documents",
        "asset_catalog.manage",
        "asset_locations.view",
        "asset_locations.manage",
        "asset_lifecycle.view",
        "assets.transition_lifecycle",
        "assets.assign",
        "assets.move",
    ],
    "Viewer": [
        "users.view",
        # Phase 1 — Asset Core: Viewer gets every *.view key only.
        "assets.view",
        "asset_locations.view",
        "asset_lifecycle.view",
    ],
}


async def sync_permissions(db) -> dict[str, Permission]:
    perm_repo = PermissionRepository(db)
    by_key: dict[str, Permission] = {}
    for module in get_registered_modules().values():
        for perm_def in module.permissions:
            existing = await perm_repo.get_by_key(perm_def.key)
            if existing is None:
                existing = Permission(key=perm_def.key, module_key=module.key, description=perm_def.description)
                db.add(existing)
                await db.flush()
            by_key[perm_def.key] = existing
    return by_key


async def sync_system_roles(db, permissions_by_key: dict[str, Permission]) -> dict[str, Role]:
    roles_by_name: dict[str, Role] = {}
    all_keys = list(permissions_by_key.keys())

    for name, keys in DEFAULT_ROLE_BUNDLES.items():
        result = await db.execute(select(Role).where(Role.name == name, Role.tenant_id.is_(None)))
        role = result.scalar_one_or_none()
        if role is None:
            role = Role(tenant_id=None, name=name, is_system_role=True)
            db.add(role)
            await db.flush()
        roles_by_name[name] = role

        grant_keys = all_keys if keys is None else keys
        existing = await db.execute(select(RolePermission.permission_id).where(RolePermission.role_id == role.id))
        existing_ids = {row[0] for row in existing}
        for key in grant_keys:
            perm = permissions_by_key[key]
            if perm.id not in existing_ids:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))

    await db.flush()
    return roles_by_name


async def ensure_tenant(db, *, name: str, subdomain: str, tier: str) -> Tenant:
    repo = TenantRepository(db)
    tenant = await repo.get_by_subdomain(subdomain)
    if tenant is None:
        tenant = repo.add(Tenant(name=name, subdomain=subdomain, subscription_tier=tier))
        await db.flush()
    return tenant


async def ensure_user(db, tenant_id, *, email: str, role: Role, password: str = SEED_PASSWORD):
    user_repo = UserRepository(db, tenant_id)
    user = await user_repo.get_by_email(email)
    service = UserService(db, tenant_id)
    if user is None:
        user = await service.create_user(email=email, phone=None, password=password, actor_user_id=None)

    assignments = await service.user_roles.list_for_user(user.id)
    if not any(a.role_id == role.id for a in assignments):
        # actor_is_platform_admin=True: every DEFAULT_ROLE_BUNDLES role is a system role
        # (sync_system_roles creates them with is_system_role=True), and seeding is itself a
        # trusted bootstrap operation, not a real user's action — see UserService.assign_role's
        # system-role escalation guard (docs/authorization.md).
        await service.assign_role(
            user_id=user.id,
            role_id=role.id,
            scope_type="tenant",
            scope_id=None,
            actor_user_id=None,
            actor_is_platform_admin=True,
        )
    return user


async def main() -> None:
    register_all_modules()

    async with AsyncSessionLocal() as db:
        permissions_by_key = await sync_permissions(db)
        roles_by_name = await sync_system_roles(db, permissions_by_key)
        await db.commit()

    async with AsyncSessionLocal() as db:
        # --- platform operator tenant + Platform Admin ---------------------------------
        platform_tenant = await ensure_tenant(db, name="Zonovia Platform", subdomain="platform", tier="platform")
        await set_tenant_session_var(db, platform_tenant.id, local=False)
        await ensure_user(db, platform_tenant.id, email="platformadmin@zonovia.example", role=roles_by_name["Platform Admin"])
        await db.commit()

    async with AsyncSessionLocal() as db:
        # --- demo tenant, one user per role bundle --------------------------------------
        tenant = await ensure_tenant(db, name="Acme Corporation", subdomain="acme-demo", tier="basic")
        await set_tenant_session_var(db, tenant.id, local=False)

        demo_users = [
            ("admin@zonovia.example", "Tenant Admin"),
            ("member@zonovia.example", "Member"),
            ("viewer@zonovia.example", "Viewer"),
        ]
        for email, role_name in demo_users:
            await ensure_user(db, tenant.id, email=email, role=roles_by_name[role_name])
        await db.commit()

    print("Seed complete.\n")
    print("Platform (tenant_slug='platform'):")
    print(f"  platformadmin@zonovia.example / {SEED_PASSWORD}")
    print("\nAcme Corporation (tenant_slug='acme-demo'):")
    for email, role_name in demo_users:
        print(f"  {email} / {SEED_PASSWORD}  ({role_name})")


if __name__ == "__main__":
    asyncio.run(main())
