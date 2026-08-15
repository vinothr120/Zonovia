import uuid

import pytest

from app.core.security import (
    TokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("Sup3rSecret!")
    assert hashed != "Sup3rSecret!"
    assert verify_password("Sup3rSecret!", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, tenant_id=tenant_id, is_platform_admin=True)
    payload = decode_token(token, expected_type=TokenType.ACCESS)
    assert payload["sub"] == str(user_id)
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["platform_admin"] is True


def test_refresh_token_rejected_as_access_token():
    token = create_refresh_token(user_id=uuid.uuid4(), tenant_id=uuid.uuid4())
    with pytest.raises(TokenError):
        decode_token(token, expected_type=TokenType.ACCESS)


def test_garbage_token_rejected():
    with pytest.raises(TokenError):
        decode_token("not-a-real-token", expected_type=TokenType.ACCESS)
