import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_repository import TenantScopedRepository
from app.users.models import Permission, Role, RolePermission, User, UserRole


class UserRepository(TenantScopedRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        stmt = self._base_query().where(User.email == email.lower())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class RoleRepository:
    """Roles are partly tenant-scoped, partly global system roles, so this doesn't use
    TenantScopedRepository's tenant-only filtering — it explicitly includes tenant_id IS NULL."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def get_by_id(self, role_id: uuid.UUID) -> Role | None:
        stmt = select(Role).where(
            Role.id == role_id,
            Role.deleted_at.is_(None),
            (Role.tenant_id == self.tenant_id) | (Role.tenant_id.is_(None)),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_available(self) -> list[Role]:
        stmt = select(Role).where(
            Role.deleted_at.is_(None),
            (Role.tenant_id == self.tenant_id) | (Role.tenant_id.is_(None)),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Role | None:
        stmt = select(Role).where(
            Role.name == name,
            (Role.tenant_id == self.tenant_id) | (Role.tenant_id.is_(None)),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class PermissionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_key(self, key: str) -> Permission | None:
        result = await self.session.execute(select(Permission).where(Permission.key == key))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Permission]:
        result = await self.session.execute(select(Permission).order_by(Permission.module_key, Permission.key))
        return list(result.scalars().all())

    async def list_for_role(self, role_id: uuid.UUID) -> list[Permission]:
        stmt = (
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class UserRoleRepository(TenantScopedRepository[UserRole]):
    """UserRole has no deleted_at — revoking a role assignment hard-deletes the row (see
    UserService.revoke_role), so the base query is overridden rather than relying on
    TenantScopedRepository's default deleted_at filter, same as AuditLogRepository."""

    model = UserRole

    def _base_query(self, *, include_deleted: bool = False):  # noqa: ARG002 — signature matches the base class it overrides
        return select(self.model).where(self.model.tenant_id == self.tenant_id)

    async def list_for_user(self, user_id: uuid.UUID) -> list[UserRole]:
        stmt = self._base_query().where(UserRole.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_user_ids_for_role(self, role_id: uuid.UUID) -> list[uuid.UUID]:
        """Used to invalidate every affected user's cached effective-permissions entry when
        a custom role's permission set changes — see UserService.update_role_permissions."""
        stmt = select(UserRole.user_id).where(UserRole.tenant_id == self.tenant_id, UserRole.role_id == role_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
