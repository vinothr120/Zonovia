import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import settings

_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def _create_token(
    *,
    subject: uuid.UUID,
    tenant_id: uuid.UUID,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "tenant_id": str(tenant_id),
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(*, user_id: uuid.UUID, tenant_id: uuid.UUID, is_platform_admin: bool = False) -> str:
    return _create_token(
        subject=user_id,
        tenant_id=tenant_id,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims={"platform_admin": is_platform_admin},
    )


def create_refresh_token(*, user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return _create_token(
        subject=user_id,
        tenant_id=tenant_id,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


class TokenError(Exception):
    pass


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid") from exc

    if payload.get("type") != expected_type.value:
        raise TokenError(f"Expected a {expected_type.value} token")
    return payload
