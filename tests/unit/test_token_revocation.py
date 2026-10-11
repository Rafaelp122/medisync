"""Unit tests for distributed and in-memory JWT token revocation."""

from unittest.mock import AsyncMock

import pytest
from src.modules.auth.infrastructure.valkey_token_revocation import (
    MemoryTokenRevocation,
    ValkeyTokenRevocation,
)


@pytest.mark.asyncio
async def test_memory_token_revocation() -> None:
    store = MemoryTokenRevocation()
    assert await store.is_revogado("jti-123") is False

    await store.revogar("jti-123")
    assert await store.is_revogado("jti-123") is True
    assert await store.is_revogado("jti-other") is False


@pytest.mark.asyncio
async def test_valkey_token_revocation() -> None:
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=0)
    mock_redis.set = AsyncMock(return_value=True)
    store = ValkeyTokenRevocation(valkey=mock_redis)

    assert await store.is_revogado("jti-abc") is False
    mock_redis.exists.assert_awaited_once_with("auth:revoked:jti-abc")

    await store.revogar("jti-abc", exp_segundos=3600)
    mock_redis.set.assert_awaited_once_with("auth:revoked:jti-abc", "1", ex=3600)

    mock_redis.exists = AsyncMock(return_value=1)
    assert await store.is_revogado("jti-abc") is True


@pytest.mark.asyncio
async def test_core_authz_is_token_revoked_and_revoke() -> None:
    from unittest.mock import patch

    from src.core.authz.revocation import is_token_revoked, revoke_token_id

    mock_client = AsyncMock()
    mock_client.exists = AsyncMock(return_value=1)
    mock_client.set = AsyncMock(return_value=True)

    with patch("src.core.authz.revocation.Redis", return_value=mock_client):
        assert await is_token_revoked("uuid-test-jti") is True
        mock_client.exists.assert_awaited_once_with("auth:revoked:uuid-test-jti")

        await revoke_token_id("uuid-test-jti", ttl_seconds=300)
        mock_client.set.assert_awaited_once_with(
            "auth:revoked:uuid-test-jti", "1", ex=300
        )
