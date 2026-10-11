"""Core presentation and diagnostic schemas."""

from pydantic import BaseModel, ConfigDict

__all__ = ["HealthCheckResponse", "ValkeyHealth"]


class ValkeyHealth(BaseModel):
    """Valkey health and operational telemetry data."""

    model_config = ConfigDict(frozen=True)

    status: str
    ping: bool
    version: str | None = None
    connected_clients: int | None = None
    used_memory_human: str | None = None
    used_memory_peak_human: str | None = None
    uptime_in_seconds: int | None = None
    error: str | None = None


class HealthCheckResponse(BaseModel):
    """System health check and observability telemetry envelope."""

    model_config = ConfigDict(frozen=True)

    status: str
    version: str
    tenant_id: int | None
    request_id: str | None
    valkey: ValkeyHealth | None = None
