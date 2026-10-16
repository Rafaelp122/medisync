"""Unit tests for queue composition root and lifespan hooks."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.asyncio import ConnectionPool, Redis
from src.modules.queue.composition import on_startup


@pytest.mark.asyncio
async def test_on_startup_default_pool() -> None:
    """Verify on_startup resolves default Valkey pool and preloads Lua scripts."""
    mock_default_pool = MagicMock(spec=ConnectionPool)
    mock_client = AsyncMock(spec=Redis)
    mock_script_manager = MagicMock()
    mock_script_manager.preload_scripts = AsyncMock(
        return_value={"alocar_chamada": "sha123"}
    )

    with (
        patch(
            "src.modules.queue.composition.get_valkey_pool",
            return_value=mock_default_pool,
        ) as mock_get_pool,
        patch(
            "src.modules.queue.composition.Redis",
            return_value=mock_client,
        ) as mock_redis_cls,
        patch(
            "src.modules.queue.composition.get_lua_script_manager",
            return_value=mock_script_manager,
        ),
    ):
        await on_startup()

        mock_get_pool.assert_called_once_with()
        mock_redis_cls.assert_called_once_with(connection_pool=mock_default_pool)
        mock_script_manager.preload_scripts.assert_awaited_once_with(mock_client)
        mock_client.aclose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_startup_explicit_pool() -> None:
    """Verify on_startup uses explicitly provided pool without get_valkey_pool."""
    explicit_pool = MagicMock(spec=ConnectionPool)
    mock_client = AsyncMock(spec=Redis)
    mock_script_manager = MagicMock()
    mock_script_manager.preload_scripts = AsyncMock(
        return_value={"alocar_chamada": "sha123"}
    )

    with (
        patch("src.modules.queue.composition.get_valkey_pool") as mock_get_pool,
        patch(
            "src.modules.queue.composition.Redis",
            return_value=mock_client,
        ) as mock_redis_cls,
        patch(
            "src.modules.queue.composition.get_lua_script_manager",
            return_value=mock_script_manager,
        ),
    ):
        await on_startup(pool=explicit_pool)

        mock_get_pool.assert_not_called()
        mock_redis_cls.assert_called_once_with(connection_pool=explicit_pool)
        mock_script_manager.preload_scripts.assert_awaited_once_with(mock_client)
        mock_client.aclose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_startup_closes_client_on_exception() -> None:
    """Verify client.aclose() is always awaited even if script preload fails."""
    explicit_pool = MagicMock(spec=ConnectionPool)
    mock_client = AsyncMock(spec=Redis)
    mock_script_manager = MagicMock()
    mock_script_manager.preload_scripts = AsyncMock(
        side_effect=RuntimeError("Lua script error")
    )

    with (
        patch("src.modules.queue.composition.Redis", return_value=mock_client),
        patch(
            "src.modules.queue.composition.get_lua_script_manager",
            return_value=mock_script_manager,
        ),
        pytest.raises(RuntimeError, match="Lua script error"),
    ):
        await on_startup(pool=explicit_pool)

    mock_client.aclose.assert_awaited_once_with()
