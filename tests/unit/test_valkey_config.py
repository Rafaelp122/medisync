"""Unit tests for Valkey config, pool initialization, and telemetry."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from redis.asyncio import ConnectionPool
from src.core.config import Settings
from src.core.valkey import (
    check_valkey_health,
    close_valkey_pool,
    get_valkey_pool,
)


def test_valkey_config_defaults() -> None:
    """Verify default Valkey configuration values and types."""
    settings = Settings()
    assert settings.VALKEY_HOST == "localhost"
    assert settings.VALKEY_PORT == 6379
    assert settings.VALKEY_MAX_CONNECTIONS == 50
    assert settings.VALKEY_SOCKET_TIMEOUT == 5.0
    assert settings.VALKEY_CONNECT_TIMEOUT == 5.0
    assert settings.VALKEY_HEALTH_CHECK_INTERVAL == 30
    assert settings.VALKEY_RETRY_ATTEMPTS == 3


def test_valkey_url_scheme_normalization() -> None:
    """Ensure valkey schemes are normalized for redis-py compatibility."""
    s1 = Settings(VALKEY_URL="valkey://localhost:6379/0")
    assert s1.async_valkey_url == "redis://localhost:6379/0"

    s2 = Settings(VALKEY_URL="valkeys://secure-host:6380/2")
    assert s2.async_valkey_url == "rediss://secure-host:6380/2"

    s3 = Settings(VALKEY_URL="redis://localhost:6379/1")
    assert s3.async_valkey_url == "redis://localhost:6379/1"


def test_get_valkey_pool_singleton() -> None:
    """Ensure get_valkey_pool returns a singleton ConnectionPool instance."""
    pool1 = get_valkey_pool()
    pool2 = get_valkey_pool()
    assert isinstance(pool1, ConnectionPool)
    assert pool1 is pool2


@pytest.mark.asyncio
async def test_close_valkey_pool() -> None:
    """Verify graceful pool closure resets the singleton instance."""
    pool = get_valkey_pool()
    assert pool is not None
    await close_valkey_pool()

    # Getting pool again creates a new instance
    new_pool = get_valkey_pool()
    assert new_pool is not pool
    await close_valkey_pool()


@pytest.mark.asyncio
async def test_check_valkey_health_healthy() -> None:
    """Verify check_valkey_health parses info and ping successfully."""
    mock_client = AsyncMock()
    mock_client.ping.return_value = True

    async def mock_info(section: str | None = None) -> dict[str, Any]:
        return {
            "memory": {
                "used_memory_human": "2.40M",
                "used_memory_peak_human": "3.10M",
            },
            "clients": {"connected_clients": 5},
            "server": {
                "valkey_version": "8.0.0",
                "uptime_in_seconds": 3600,
            },
        }.get(section or "", {})

    mock_client.info.side_effect = mock_info

    health = await check_valkey_health(mock_client)
    assert health["status"] == "healthy"
    assert health["ping"] is True
    assert health["version"] == "8.0.0"
    assert health["connected_clients"] == 5
    assert health["used_memory_human"] == "2.40M"
    assert health["used_memory_peak_human"] == "3.10M"
    assert health["uptime_in_seconds"] == 3600


@pytest.mark.asyncio
async def test_check_valkey_health_redis_version_fallback() -> None:
    """Verify fallback to redis_version when valkey_version is absent."""
    mock_client = AsyncMock()
    mock_client.ping.return_value = True

    async def mock_info(section: str | None = None) -> dict[str, Any]:
        return {
            "memory": {"used_memory_human": "1.00M"},
            "clients": {"connected_clients": 1},
            "server": {"redis_version": "7.2.4", "uptime_in_seconds": 120},
        }.get(section or "", {})

    mock_client.info.side_effect = mock_info

    health = await check_valkey_health(mock_client)
    assert health["status"] == "healthy"
    assert health["version"] == "7.2.4"


@pytest.mark.asyncio
async def test_check_valkey_health_unhealthy_on_exception() -> None:
    """Verify check_valkey_health returns unhealthy on connection failure."""
    mock_client = AsyncMock()
    mock_client.ping.side_effect = ConnectionError("Connection refused")

    health = await check_valkey_health(mock_client)
    assert health["status"] == "unhealthy"
    assert health["ping"] is False
    assert "Connection refused" in health["error"]
