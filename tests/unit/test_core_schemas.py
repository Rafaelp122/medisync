"""Unit tests for core telemetry schemas (ValkeyHealth and HealthCheckResponse)."""

import pytest
from pydantic import ValidationError
from src.core.schemas import HealthCheckResponse, ValkeyHealth


def test_valkey_health_frozen_and_valid() -> None:
    """Verifica instanciação e imutabilidade de ValkeyHealth."""
    vh = ValkeyHealth(
        status="healthy",
        ping=True,
        version="8.0.1",
        connected_clients=5,
        used_memory_human="2.5M",
        used_memory_peak_human="4.1M",
        uptime_in_seconds=3600,
    )
    assert vh.status == "healthy"
    assert vh.ping is True
    assert vh.version == "8.0.1"

    with pytest.raises(ValidationError):
        vh.status = "unhealthy"  # type: ignore[misc]


def test_healthcheck_response_frozen_and_valid() -> None:
    """Verifica instanciação e imutabilidade de HealthCheckResponse."""
    vh = ValkeyHealth(status="ok", ping=True)
    resp = HealthCheckResponse(
        status="ok",
        version="0.1.0",
        tenant_id=42,
        request_id="0192e100-0000-7000-8000-000000000001",
        valkey=vh,
    )
    assert resp.status == "ok"
    assert resp.tenant_id == 42
    assert resp.valkey is not None
    assert resp.valkey.ping is True

    with pytest.raises(ValidationError):
        resp.status = "error"  # type: ignore[misc]
