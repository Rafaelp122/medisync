"""Asynchronous Valkey client pool, lifecycle, and healthcheck telemetry."""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from typing import Any

from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff

from src.core.config import get_settings

_valkey_pool: ConnectionPool | None = None
_valkey_pool_loop: asyncio.AbstractEventLoop | None = None


def get_valkey_pool() -> ConnectionPool:
    """Retrieve or create the Valkey ConnectionPool for the active event loop."""
    global _valkey_pool, _valkey_pool_loop

    current_loop: asyncio.AbstractEventLoop | None = None
    with contextlib.suppress(RuntimeError):
        current_loop = asyncio.get_running_loop()

    if (
        _valkey_pool is not None
        and current_loop is not None
        and _valkey_pool_loop is not current_loop
    ):
        _valkey_pool = None
        _valkey_pool_loop = None

    if _valkey_pool is None:
        settings = get_settings()
        retry_strategy = Retry(
            backoff=ExponentialBackoff(),
            retries=settings.VALKEY_RETRY_ATTEMPTS,
        )
        _valkey_pool = ConnectionPool.from_url(  # pyright: ignore[reportUnknownMemberType]
            settings.async_valkey_url,
            max_connections=settings.VALKEY_MAX_CONNECTIONS,
            socket_timeout=settings.VALKEY_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.VALKEY_CONNECT_TIMEOUT,
            health_check_interval=settings.VALKEY_HEALTH_CHECK_INTERVAL,
            retry=retry_strategy,
            retry_on_timeout=True,
            decode_responses=True,
        )
        _valkey_pool_loop = current_loop

    return _valkey_pool


async def close_valkey_pool() -> None:
    """Gracefully disconnect and tear down the Valkey connection pool."""
    global _valkey_pool, _valkey_pool_loop
    if _valkey_pool is not None:
        with contextlib.suppress(Exception):
            await _valkey_pool.disconnect()
        _valkey_pool = None
        _valkey_pool_loop = None


async def get_valkey_client() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency yielding an asynchronous Valkey Redis client."""
    pool = get_valkey_pool()
    client = Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.aclose()


async def check_valkey_health(client: Redis) -> dict[str, Any]:
    """Perform healthcheck on Valkey instance, verifying ping and telemetry."""
    try:
        is_alive = bool(await client.ping())  # pyright: ignore[reportUnknownMemberType]
        mem: dict[str, Any] = await client.info("memory")  # pyright: ignore[reportUnknownMemberType]
        clients: dict[str, Any] = await client.info("clients")  # pyright: ignore[reportUnknownMemberType]
        server: dict[str, Any] = await client.info("server")  # pyright: ignore[reportUnknownMemberType]
        return {
            "status": "healthy" if is_alive else "unhealthy",
            "ping": is_alive,
            "version": str(
                server.get("valkey_version") or server.get("redis_version") or "unknown"
            ),
            "connected_clients": int(clients.get("connected_clients", 0)),
            "used_memory_human": str(mem.get("used_memory_human", "unknown")),
            "used_memory_peak_human": str(mem.get("used_memory_peak_human", "unknown")),
            "uptime_in_seconds": int(server.get("uptime_in_seconds", 0)),
        }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "ping": False,
            "error": str(exc),
        }
