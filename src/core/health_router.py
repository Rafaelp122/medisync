"""System health check and diagnostic routing module."""

from fastapi import APIRouter

from src.core.config import get_settings
from src.core.context import get_current_request_id, get_current_tenant_id
from src.core.dependencies import ValkeyDep
from src.core.schemas import HealthCheckResponse, ValkeyHealth
from src.core.valkey import check_valkey_health

__all__ = ["health_router"]

health_router = APIRouter(tags=["System Health"])


@health_router.get("/healthz")
async def healthcheck(
    valkey_client: ValkeyDep,
) -> HealthCheckResponse:
    """Return system health status and Valkey telemetry."""
    settings = get_settings()
    valkey_telemetry: ValkeyHealth | None = None
    try:
        raw_health = await check_valkey_health(valkey_client)
        valkey_telemetry = ValkeyHealth(**raw_health)
    except Exception as exc:
        valkey_telemetry = ValkeyHealth(status="unhealthy", ping=False, error=str(exc))

    return HealthCheckResponse(
        status="ok",
        version=settings.APP_VERSION,
        tenant_id=get_current_tenant_id(),
        request_id=get_current_request_id(),
        valkey=valkey_telemetry,
    )
