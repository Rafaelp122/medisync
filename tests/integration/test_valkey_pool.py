"""Integration tests for Valkey pool, concurrency, and /healthz."""

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from src.core.valkey import (
    check_valkey_health,
    close_valkey_pool,
    get_valkey_client,
    get_valkey_pool,
)
from src.main import create_app


@pytest.fixture(autouse=True)
async def cleanup_valkey_pool() -> AsyncGenerator[None]:
    """Ensure pool is gracefully closed after integration tests."""
    yield
    await close_valkey_pool()


@pytest.mark.asyncio
async def test_valkey_client_dependency_crud() -> None:
    """Verify live CRUD operations using get_valkey_client dependency."""
    async for client in get_valkey_client():
        assert await client.ping() is True  # pyright: ignore[reportUnknownMemberType]
        key = "integration:test:key"
        await client.set(key, "medisync_val", ex=10)
        val = await client.get(key)
        assert val == "medisync_val"
        await client.delete(key)
        assert await client.get(key) is None


@pytest.mark.asyncio
async def test_valkey_pool_concurrency() -> None:
    """Verify pool supports 50 concurrent async tasks without connection exhaustion."""
    pool = get_valkey_pool()

    async def worker(worker_id: int) -> bool:
        client = Redis(connection_pool=pool)
        try:
            key = f"concurrency:worker:{worker_id}"
            await client.set(key, f"val_{worker_id}", ex=5)
            val = await client.get(key)
            assert val == f"val_{worker_id}"
            await client.delete(key)
            return True
        finally:
            await client.aclose()

    tasks = [worker(i) for i in range(50)]
    results = await asyncio.gather(*tasks)
    assert len(results) == 50
    assert all(results)


@pytest.mark.asyncio
async def test_check_valkey_health_live() -> None:
    """Verify check_valkey_health against live running Valkey container."""
    async for client in get_valkey_client():
        health = await check_valkey_health(client)
        assert health["status"] == "healthy"
        assert health["ping"] is True
        assert "version" in health
        assert health["connected_clients"] >= 1
        assert "used_memory_human" in health
        assert health["uptime_in_seconds"] > 0


@pytest.mark.asyncio
async def test_healthz_endpoint_with_live_valkey() -> None:
    """Verify /healthz returns 200 with comprehensive Valkey metrics."""
    test_app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        res = await client.get("/healthz")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "valkey" in data
        assert data["valkey"]["status"] == "healthy"
        assert data["valkey"]["ping"] is True
        assert data["valkey"]["connected_clients"] >= 1
        assert data["valkey"]["used_memory_human"] is not None


@pytest.mark.asyncio
async def test_healthz_endpoint_handles_valkey_failure() -> None:
    """Verify /healthz gracefully degrades when Valkey connection fails."""
    test_app = create_app()

    async def broken_client() -> AsyncMock:
        mock = AsyncMock(spec=Redis)
        mock.ping.side_effect = ConnectionError("Simulated Valkey Outage")
        return mock

    test_app.dependency_overrides[get_valkey_client] = broken_client

    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            res = await client.get("/healthz")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "ok"
            assert data["valkey"]["status"] == "unhealthy"
            assert data["valkey"]["ping"] is False
            assert "Simulated Valkey Outage" in data["valkey"]["error"]
    finally:
        test_app.dependency_overrides.clear()
