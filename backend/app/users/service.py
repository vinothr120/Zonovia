import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.cache import get_cached_json, invalidate, permission_cache_key, set_cached_json
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationAppError
from app.core.security import hash_password
from app.users.models import Role, User, UserRole
from app.users.repository import PermissionRepository, RoleRepository, UserRepository, UserRoleRepository


@dataclass(frozen=True)
class PermissionGrant:
    permission_key: str
    scope_type: str
    scope_id: str | None


def grant_covers(grant: PermissionGrant, key: str) -> bool:
    """Phase 0 only implements tenant-wide scope — a grant with `scope_type="tenant"` covers
    everything; there is no location concept to scope narrower against yet (`AssetLocation`
    is Asset Core, Phase 1). Kept as a standalone predicate (rather than inlining the check)
    so Phase 1's location-scoped roles are a change to this one function, not to every call
    site — see UserRole's docstring and docs/authorization.md."""
    if grant.permission_key != key:
        return False
    return grant.scope_type == "tenant"


class UserService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.users = UserRepository(session, tenant_id)
        self.roles = RoleRepository(session, tenant_id)
        self.permissions = PermissionRepository(session)
        self.user_roles = UserRoleRepository(session, tenant_id)

    async def create_user(self, *, email: str, phone: str | None, password: str, actor_user_id: uuid.UUID | None) -> User:
        email = email.lower().strip()
        if await self.users.get_by_email(email) is not None:
            raise ConflictError(f"A user with email {email} already exists in this tenant.")

        user = self.users.add(User(email=email, phone=phone, password_hash=hash_password(password), status="active"))
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="user.created",
            entity_type="user",
            entity_id=user.id,
            new_value={"email": email},
        )
        return user

    async def get_user_or_404(self, user_id: uuid.UUID) -> User:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    async def assign_role(
        self,
        *,
        user_id: uuid.UUID,
        role_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        actor_is_platform_admin: bool = False,
    ) -> UserRole:
        user = await self.get_user_or_404(user_id)
        role = await self.roles.get_by_id(role_id)
        if role is None:
            raise NotFoundError("Role not found.")
        if role.is_system_role and not actor_is_platform_admin:
            # System role bundles (Platform Admin, Tenant Admin, ...) are shared across every
            # tenant and carry tenant-wide/platform-wide reach — roles.manage alone (held by
            # any Tenant Admin) must not be enough to self-escalate to Platform Admin. Only a
            # platform admin may grant a system role; custom tenant-scoped roles are unaffected.
            raise PermissionDeniedError("Only a platform administrator can assign a system role.")
        if scope_type != "tenant":
            raise ValidationAppError("Only tenant-wide role scope is supported in this release.")

        assignment = self.user_roles.add(UserRole(user_id=user.id, role_id=role.id, scope_type=scope_type, scope_id=scope_id))
        await self.session.flush()
        await invalidate(permission_cache_key(str(user.id)))
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="user_role.assigned",
            entity_type="user",
            entity_id=user.id,
            new_value={"role_id": str(role.id), "scope_type": scope_type, "scope_id": str(scope_id) if scope_id else None},
        )
        return assignment

    async def create_role(self, *, name: str, permission_keys: list[str], actor_user_id: uuid.UUID | None) -> Role:
        """Custom, tenant-scoped role — always is_system_role=False (the seeded bundles in
        seed.py::DEFAULT_ROLE_BUNDLES are the only is_system_role=True rows, tenant_id=None,
        shared across every tenant; those are never created or edited through this API)."""
        role = Role(tenant_id=self.tenant_id, name=name, is_system_role=False)
        self.session.add(role)
        await self.session.flush()
        await self._set_role_permissions(role, permission_keys)
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="role.created",
            entity_type="role",
            entity_id=role.id,
            new_value={"name": name, "permission_keys": permission_keys},
        )
        return role

    async def update_role_permissions(
        self, *, role_id: uuid.UUID, permission_keys: list[str], actor_user_id: uuid.UUID | None
    ) -> Role:
        role = await self.roles.get_by_id(role_id)
        if role is None:
            raise NotFoundError("Role not found.")
        if role.is_system_role:
            raise ValidationAppError("System roles cannot be edited — create a custom role instead.")

        await self._set_role_permissions(role, permission_keys)
        for user_id in await self.user_roles.list_user_ids_for_role(role.id):
            await invalidate(permission_cache_key(str(user_id)))
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="role.permissions_updated",
            entity_type="role",
            entity_id=role.id,
            new_value={"permission_keys": permission_keys},
        )
        return role

    async def _set_role_permissions(self, role: Role, permission_keys: list[str]) -> None:
        from sqlalchemy import delete

        from app.users.models import RolePermission

        await self.session.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        for key in permission_keys:
            permission = await self.permissions.get_by_key(key)
            if permission is None:
                raise ValidationAppError(f"Unknown permission key: {key}")
            self.session.add(RolePermission(role_id=role.id, permission_id=permission.id))
        await self.session.flush()

    async def revoke_role(self, *, user_role_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        assignment = await self.user_roles.get_by_id(user_role_id)
        if assignment is None:
            raise NotFoundError("Role assignment not found.")
        user_id = assignment.user_id
        await self.session.delete(assignment)
        await self.session.flush()
        await invalidate(permission_cache_key(str(user_id)))
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="user_role.revoked",
            entity_type="user",
            entity_id=user_id,
            old_value={"user_role_id": str(user_role_id)},
        )

    async def get_effective_grants(self, user_id: uuid.UUID, *, use_cache: bool = True) -> list[PermissionGrant]:
        cache_key = permission_cache_key(str(user_id))
        if use_cache:
            cached = await get_cached_json(cache_key)
            if cached is not None:
                return [PermissionGrant(**g) for g in cached]

        assignments = await self.user_roles.list_for_user(user_id)
        grants: list[PermissionGrant] = []
        for assignment in assignments:
            perms = await self.permissions.list_for_role(assignment.role_id)
            for perm in perms:
                grants.append(
                    PermissionGrant(
                        permission_key=perm.key,
                        scope_type=assignment.scope_type,
                        scope_id=str(assignment.scope_id) if assignment.scope_id else None,
                    )
                )

        if use_cache:
            await set_cached_json(cache_key, [g.__dict__ for g in grants], ttl_seconds=300)
        return grants
