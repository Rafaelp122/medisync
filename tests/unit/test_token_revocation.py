"""Unit tests for unified fail-closed TokenRevocationPort and adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
import src.core.authz.revocation as revocation_mod
from src.core.authz.revocation import (
    MemoryTokenRevocation,
    TokenRevocationPort,
    ValkeyTokenRevocation,
    get_token_revocation,
)
from src.core.config import get_settings
from src.core.errors import ServiceUnavailableError

if TYPE_CHECKING:
    from redis.asyncio import ConnectionPool, Redis


class FakeRevocationRedis:
    """Named in-memory fake for async Redis client in token revocation tests."""

    def __init__(
        self,
        *,
        initial_revoked: set[str] | None = None,
        error_on_exists: Exception | None = None,
        error_on_set: Exception | None = None,
    ) -> None:
        self.revoked = set(initial_revoked or set())
        self.error_on_exists = error_on_exists
        self.error_on_set = error_on_set
        self.exists_calls: list[str] = []
        self.set_calls: list[tuple[str, str, int | None]] = []
        self.closed = False

    async def exists(self, key: str) -> int:
        self.exists_calls.append(key)
        if self.error_on_exists is not None:
            raise self.error_on_exists
        return 1 if key in self.revoked else 0

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        self.set_calls.append((key, value, ex))
        if self.error_on_set is not None:
            raise self.error_on_set
        if nx and key in self.revoked:
            return False
        self.revoked.add(key)
        return True

    async def aclose(self) -> None:
        self.closed = True


class FakeConnectionPool:
    """Minimal named connection pool stub for owned-client lifecycle tests."""

    pass


@pytest.mark.asyncio
async def test_memory_token_revocation() -> None:
    """MemoryTokenRevocation tracks revoked JTIs in memory and supports clear."""
    store = MemoryTokenRevocation()
    assert isinstance(store, TokenRevocationPort)
    assert await store.is_revogado("jti-123") is False

    await store.revogar("jti-123")
    assert await store.is_revogado("jti-123") is True
    assert await store.is_revogado("jti-other") is False

    store.clear()
    assert await store.is_revogado("jti-123") is False


@pytest.mark.asyncio
async def test_valkey_token_revocation_with_injected_client() -> None:
    """ValkeyTokenRevocation delegates to injected Redis without closing it."""
    fake_redis = FakeRevocationRedis()
    store = ValkeyTokenRevocation(valkey=cast("Redis", fake_redis))
    assert isinstance(store, TokenRevocationPort)

    assert await store.is_revogado("jti-abc") is False
    assert fake_redis.exists_calls == ["auth:revoked:jti-abc"]

    await store.revogar("jti-abc", exp_segundos=3600)
    assert fake_redis.set_calls == [("auth:revoked:jti-abc", "1", 3600)]
    assert await store.is_revogado("jti-abc") is True
    assert fake_redis.closed is False


@pytest.mark.asyncio
async def test_valkey_token_revocation_is_fail_closed_on_valkey_errors() -> None:
    """Valkey failures or timeouts raise ServiceUnavailableError (503), never False."""
    for exc in (ConnectionError("valkey down"), TimeoutError("valkey timeout")):
        failing_redis = FakeRevocationRedis(error_on_exists=exc, error_on_set=exc)
        store = ValkeyTokenRevocation(valkey=cast("Redis", failing_redis))

        with pytest.raises(ServiceUnavailableError) as err_check:
            await store.is_revogado("jti-fail")
        assert err_check.value.status_code == 503
        assert "jti-fail" in err_check.value.detail

        with pytest.raises(ServiceUnavailableError) as err_set:
            await store.revogar("jti-fail", exp_segundos=60)
        assert err_set.value.status_code == 503
        assert "jti-fail" in err_set.value.detail


@pytest.mark.asyncio
async def test_valkey_token_revocation_closes_owned_client_on_success_and_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When valkey=None, owned Redis client is always closed via aclose()."""
    created_clients: list[FakeRevocationRedis] = []
    pool = FakeConnectionPool()

    def _build_client(*, connection_pool: Any) -> FakeRevocationRedis:
        assert connection_pool is pool
        client = FakeRevocationRedis(initial_revoked={"auth:revoked:jti-owned"})
        created_clients.append(client)
        return client

    monkeypatch.setattr(revocation_mod, "Redis", _build_client)
    store = ValkeyTokenRevocation(pool=cast("ConnectionPool", pool))

    assert await store.is_revogado("jti-owned") is True
    assert len(created_clients) == 1
    assert created_clients[0].closed is True

    def _build_failing_client(*, connection_pool: Any) -> FakeRevocationRedis:
        assert connection_pool is pool
        client = FakeRevocationRedis(error_on_exists=TimeoutError("read timeout"))
        created_clients.append(client)
        return client

    monkeypatch.setattr(revocation_mod, "Redis", _build_failing_client)
    with pytest.raises(ServiceUnavailableError) as err_info:
        await store.is_revogado("jti-timeout")
    assert err_info.value.status_code == 503
    assert len(created_clients) == 2
    assert created_clients[1].closed is True


def test_get_token_revocation_respects_environment_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_token_revocation selects MemoryTokenRevocation under TestSettings."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    try:
        mem_store = get_token_revocation()
        assert isinstance(mem_store, MemoryTokenRevocation)

        monkeypatch.setenv("ENVIRONMENT", "development")
        get_settings.cache_clear()
        valkey_store = get_token_revocation()
        assert isinstance(valkey_store, ValkeyTokenRevocation)
    finally:
        get_settings.cache_clear()


def test_legacy_revocation_helpers_and_duplicates_removed() -> None:
    """Orphan helpers and duplicate auth revocation modules must not exist."""
    assert not hasattr(revocation_mod, "is_token_revoked")
    assert not hasattr(revocation_mod, "revoke_token_id")
