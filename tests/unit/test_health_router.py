"""Unit tests for the system health router (/healthz)."""

from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from src.core.config import get_settings
from src.core.health_router import health_router
from src.core.logging import reset_current_request_id, set_current_request_id
from src.core.valkey import get_valkey_client

from tests.doubles import FakeValkey


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(health_router)
    return app


@pytest.mark.asyncio
async def test_healthz_endpoint_success() -> None:
    """Verify /healthz returns 200, status 'ok', and configurable APP_VERSION."""
    app = _create_test_app()

    async def _fake_valkey() -> AsyncGenerator[Redis, None]:
        client = FakeValkey(
            info_sections={
                "memory": {
                    "used_memory_human": "2.1M",
                    "used_memory_peak_human": "3.0M",
                },
                "clients": {"connected_clients": 4},
                "server": {"valkey_version": "8.0.0", "uptime_in_seconds": 1200},
            }
        )
        yield cast("Redis", client)

    app.dependency_overrides[get_valkey_client] = _fake_valkey

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == get_settings().APP_VERSION
    assert "tenant_id" not in data
    assert data["valkey"]["status"] == "healthy"
    assert data["valkey"]["ping"] is True
    assert data["valkey"]["connected_clients"] == 4


@pytest.mark.asyncio
async def test_healthz_endpoint_valkey_degraded() -> None:
    """Verify /healthz returns 200 even when Valkey connection fails."""
    app = _create_test_app()

    async def _failing_valkey() -> AsyncGenerator[Redis, None]:
        client = FakeValkey(ping_error=ConnectionError("Connection refused"))
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
    """Verify request_id propagation in /healthz without tenant_id."""
    app = _create_test_app()

    async def _fake_valkey() -> AsyncGenerator[Redis, None]:
        yield cast("Redis", FakeValkey())

    app.dependency_overrides[get_valkey_client] = _fake_valkey

    req_token = set_current_request_id("req-test-1234")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/healthz")

        assert resp.status_code == 200
        data = resp.json()
        assert "tenant_id" not in data
        assert data["request_id"] == "req-test-1234"
    finally:
        reset_current_request_id(req_token)


@pytest.mark.asyncio
async def test_healthz_endpoint_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify fallback when check_valkey_health raises an unexpected exception."""
    app = _create_test_app()

    async def _fake_valkey() -> AsyncGenerator[Redis, None]:
        yield cast("Redis", FakeValkey())

    app.dependency_overrides[get_valkey_client] = _fake_valkey

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
