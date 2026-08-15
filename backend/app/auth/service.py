import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import RefreshToken
from app.config import settings
from app.core.audit import write_audit_log
from app.core.base_model import as_aware_utc
from app.core.database import set_tenant_session_var
from app.core.exceptions import AccountLockedError, UnauthorizedError
from app.core.security import (
    TokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.tenants.repository import TenantRepository
from app.users.models import User
from app.users.repository import UserRepository
from app.users.service import UserService

_GENERIC_LOGIN_ERROR = "Invalid email or password."


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _is_platform_admin(db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    service = UserService(db, tenant_id)
    grants = await service.get_effective_grants(user_id, use_cache=False)
    return any(g.permission_key == "platform.manage_tenants" for g in grants)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def login(self, *, tenant_slug: str, email: str, password: str, ip_address: str | None = None) -> tuple[str, str, int]:
        tenant = await TenantRepository(self.db).get_by_subdomain(tenant_slug)
        if tenant is None or tenant.status != "active":
            raise UnauthorizedError(_GENERIC_LOGIN_ERROR)

        await set_tenant_session_var(self.db, tenant.id, local=True)
        user = await UserRepository(self.db, tenant.id).get_by_email(email)
        if user is None:
            raise UnauthorizedError(_GENERIC_LOGIN_ERROR)

        now = datetime.now(UTC)
        if user.locked_until is not None and as_aware_utc(user.locked_until) > now:
            raise AccountLockedError("Account temporarily locked due to repeated failed login attempts.")

        if not verify_password(password, user.password_hash):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.login_max_failed_attempts:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            await self.db.flush()
            await write_audit_log(
                self.db,
                tenant_id=tenant.id,
                actor_user_id=user.id,
                action="auth.login_failed",
                entity_type="user",
                entity_id=user.id,
                ip_address=ip_address,
            )
            raise UnauthorizedError(_GENERIC_LOGIN_ERROR)

        if user.status != "active":
            raise UnauthorizedError("This account is not active. Contact your tenant administrator.")

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        await self.db.flush()

        is_platform_admin = await _is_platform_admin(self.db, tenant.id, user.id)
        access_token, refresh_token, expires_in = await self._issue_tokens(
            user_id=user.id, tenant_id=tenant.id, is_platform_admin=is_platform_admin
        )

        await write_audit_log(
            self.db,
            tenant_id=tenant.id,
            actor_user_id=user.id,
            action="auth.login_success",
            entity_type="user",
            entity_id=user.id,
            ip_address=ip_address,
        )
        return access_token, refresh_token, expires_in

    async def _issue_tokens(self, *, user_id: uuid.UUID, tenant_id: uuid.UUID, is_platform_admin: bool) -> tuple[str, str, int]:
        access_token = create_access_token(user_id=user_id, tenant_id=tenant_id, is_platform_admin=is_platform_admin)
        refresh_token = create_refresh_token(user_id=user_id, tenant_id=tenant_id)

        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        self.db.add(
            RefreshToken(tenant_id=tenant_id, user_id=user_id, token_hash=_hash_token(refresh_token), expires_at=expires_at)
        )
        await self.db.flush()
        return access_token, refresh_token, settings.access_token_expire_minutes * 60

    async def refresh(self, *, refresh_token: str) -> tuple[str, str, int]:
        try:
            payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
        except TokenError as exc:
            raise UnauthorizedError(str(exc)) from exc

        tenant_id = uuid.UUID(payload["tenant_id"])
        user_id = uuid.UUID(payload["sub"])
        await set_tenant_session_var(self.db, tenant_id, local=True)

        token_hash = _hash_token(refresh_token)
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.tenant_id == tenant_id,
                RefreshToken.token_hash == token_hash,
                RefreshToken.deleted_at.is_(None),
            )
        )
        stored = result.scalar_one_or_none()
        now = datetime.now(UTC)
        if stored is None or stored.revoked_at is not None or as_aware_utc(stored.expires_at) < now:
            raise UnauthorizedError("Refresh token is invalid or has expired.")

        stored.revoked_at = now  # rotate: this token is now single-use

        user = await UserRepository(self.db, tenant_id).get_by_id(user_id)
        if user is None or user.status != "active":
            raise UnauthorizedError("User account is not active.")

        is_platform_admin = await _is_platform_admin(self.db, tenant_id, user_id)
        return await self._issue_tokens(user_id=user_id, tenant_id=tenant_id, is_platform_admin=is_platform_admin)

    async def logout(self, *, refresh_token: str) -> None:
        try:
            payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
        except TokenError:
            return  # already unusable; logout is idempotent

        tenant_id = uuid.UUID(payload["tenant_id"])
        await set_tenant_session_var(self.db, tenant_id, local=True)
        token_hash = _hash_token(refresh_token)
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.tenant_id == tenant_id, RefreshToken.token_hash == token_hash)
        )
        stored = result.scalar_one_or_none()
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = datetime.now(UTC)
            await self.db.flush()
            await write_audit_log(
                self.db,
                tenant_id=tenant_id,
                actor_user_id=stored.user_id,
                action="auth.logout",
                entity_type="user",
                entity_id=stored.user_id,
            )

    async def change_password(self, *, user: User, tenant_id: uuid.UUID, current_password: str, new_password: str) -> None:
        if not verify_password(current_password, user.password_hash):
            raise UnauthorizedError("Current password is incorrect.")
        user.password_hash = hash_password(new_password)
        await self.db.flush()
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_user_id=user.id,
            action="auth.password_changed",
            entity_type="user",
            entity_id=user.id,
        )
