"""Unit tests for the system health router (/healthz)."""

from collections.abc import AsyncGenerator
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from src.core.config import get_settings
from src.core.context import (
    reset_current_request_id,
    set_current_request_id,
    tenant_context,
)
from src.core.health_router import health_router
from src.core.valkey import get_valkey_client


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(health_router)
    return app


@pytest.mark.asyncio
async def test_healthz_endpoint_success() -> None:
    """Verify /healthz returns 200, status 'ok', and configurable APP_VERSION."""
    app = _create_test_app()

    async def _mock_valkey() -> AsyncGenerator[Redis, None]:
        client = MagicMock(spec=Redis)
        client.ping = AsyncMock(return_value=True)
        info_data: dict[str, dict[str, Any]] = {
            "memory": {"used_memory_human": "2.1M", "used_memory_peak_human": "3.0M"},
            "clients": {"connected_clients": 4},
            "server": {"valkey_version": "8.0.0", "uptime_in_seconds": 1200},
        }

        def _get_info(section: str | None = None) -> dict[str, Any]:
            if section is None:
                return {}
            return info_data.get(section, {})

        client.info = AsyncMock(side_effect=_get_info)
        yield cast("Redis", client)

    app.dependency_overrides[get_valkey_client] = _mock_valkey

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == get_settings().APP_VERSION
    assert data["valkey"]["status"] == "healthy"
    assert data["valkey"]["ping"] is True
    assert data["valkey"]["connected_clients"] == 4


@pytest.mark.asyncio
async def test_healthz_endpoint_valkey_degraded() -> None:
    """Verify /healthz returns 200 even when Valkey connection fails."""
    app = _create_test_app()

    async def _failing_valkey() -> AsyncGenerator[Redis, None]:
        client = MagicMock(spec=Redis)
        client.ping = AsyncMock(side_effect=ConnectionError("Connection refused"))
        yield cast("Redis", client)

    app.dependency_overrides[get_valkey_client] = _failing_valkey

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == get_settings().APP_VERSION
    assert data["valkey"]["status"] == "unhealthy"
    assert data["valkey"]["ping"] is False
    assert "Connection refused" in data["valkey"]["error"]


@pytest.mark.asyncio
async def test_healthz_endpoint_with_context() -> None:
    """Verify tenant_id and request_id propagation in /healthz."""
    app = _create_test_app()

    async def _mock_valkey() -> AsyncGenerator[Redis, None]:
        client = MagicMock(spec=Redis)
        client.ping = AsyncMock(return_value=True)
        client.info = AsyncMock(return_value={})
        yield cast("Redis", client)

    app.dependency_overrides[get_valkey_client] = _mock_valkey

    req_token = set_current_request_id("req-test-1234")
    try:
        with tenant_context(tenant_id=42):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.get("/healthz")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == 42
        assert data["request_id"] == "req-test-1234"
    finally:
        reset_current_request_id(req_token)


@pytest.mark.asyncio
async def test_healthz_endpoint_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify fallback when check_valkey_health raises an unexpected exception."""
    app = _create_test_app()

    async def _mock_valkey() -> AsyncGenerator[Redis, None]:
        client = MagicMock(spec=Redis)
        yield cast("Redis", client)

    app.dependency_overrides[get_valkey_client] = _mock_valkey

    async def _failing_check(_client: Redis) -> dict[str, Any]:
        raise RuntimeError("Unexpected telemetry error")

    monkeypatch.setattr("src.core.health_router.check_valkey_health", _failing_check)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == get_settings().APP_VERSION
    assert data["valkey"]["status"] == "unhealthy"
    assert data["valkey"]["ping"] is False
    assert "Unexpected telemetry error" in data["valkey"]["error"]
