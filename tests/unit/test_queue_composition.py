"""Unit tests for queue composition root and lifespan hooks."""

import pytest
from redis.asyncio import ConnectionPool
from src.modules.queue import composition as queue_comp
from src.modules.queue.composition import on_startup

from tests.doubles import FakeLuaValkeyClient


@pytest.mark.asyncio
async def test_on_startup_default_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify on_startup resolves default Valkey pool and preloads Lua scripts."""
    default_pool = ConnectionPool(host="localhost", port=6379)
    fake_client = FakeLuaValkeyClient()
    captured_pools: list[ConnectionPool] = []

    def _fake_redis(*, connection_pool: ConnectionPool) -> FakeLuaValkeyClient:
        captured_pools.append(connection_pool)
        return fake_client

    monkeypatch.setattr(queue_comp, "get_valkey_pool", lambda: default_pool)
    monkeypatch.setattr(queue_comp, "Redis", _fake_redis)

    await on_startup()

    assert captured_pools == [default_pool]
    assert len(fake_client.script_load_calls) >= 2
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_on_startup_explicit_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify on_startup uses explicitly provided pool without get_valkey_pool."""
    explicit_pool = ConnectionPool(host="localhost", port=6379)
    fake_client = FakeLuaValkeyClient()
    captured_pools: list[ConnectionPool] = []
    get_pool_called = False

    def _fail_get_pool() -> ConnectionPool:
        nonlocal get_pool_called
        get_pool_called = True
        return explicit_pool

    def _fake_redis(*, connection_pool: ConnectionPool) -> FakeLuaValkeyClient:
        captured_pools.append(connection_pool)
        return fake_client

    monkeypatch.setattr(queue_comp, "get_valkey_pool", _fail_get_pool)
    monkeypatch.setattr(queue_comp, "Redis", _fake_redis)

    await on_startup(pool=explicit_pool)

    assert get_pool_called is False
    assert captured_pools == [explicit_pool]
    assert len(fake_client.script_load_calls) >= 2
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_on_startup_closes_client_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify client.aclose() is always awaited even if script preload fails."""
    explicit_pool = ConnectionPool(host="localhost", port=6379)
    fake_client = FakeLuaValkeyClient(
        script_load_outcomes=[RuntimeError("Lua script error")]
    )

    def _fake_redis(*, connection_pool: ConnectionPool) -> FakeLuaValkeyClient:
        return fake_client

    monkeypatch.setattr(queue_comp, "Redis", _fake_redis)

    with pytest.raises(RuntimeError, match="Lua script error"):
        await on_startup(pool=explicit_pool)

    assert fake_client.closed is True
