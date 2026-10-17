"""Telemetry composition root: concrete adapter wiring (DI Fase 3).

Single place in telemetry module allowed to import infrastructure adapters.
Routers and tests must resolve services via TelemetryServiceDep
and ConfigPlantaoServiceDep.
"""

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import DbSessionDep
from src.core.dependencies import ValkeyDep
from src.modules.telemetry.application.ports.telemetry_cache_port import (
    TelemetryCachePort,
)
from src.modules.telemetry.application.services.config_plantao_service import (
    ConfigPlantaoService,
)
from src.modules.telemetry.application.services.telemetry_service import (
    TelemetryService,
)
from src.modules.telemetry.infrastructure.config_plantao_repository import (
    SqlConfigPlantaoRepository,
)
from src.modules.telemetry.infrastructure.telemetry_reader_sql import (
    SqlTelemetryReader,
)
from src.modules.telemetry.infrastructure.valkey_telemetry_cache import (
    MemoryTelemetryCache,
    ValkeyTelemetryCache,
)


def resolve_telemetry_cache(valkey: Redis | None = None) -> TelemetryCachePort:
    settings = get_settings()
    if settings.TELEMETRY_CACHE_BACKEND == "memory":
        return MemoryTelemetryCache()
    return ValkeyTelemetryCache(valkey=valkey)


def build_telemetry_service_for_session(
    session: AsyncSession,
    valkey: Redis | None = None,
    cache_ttl_segundos: int | None = None,
) -> TelemetryService:
    """Build TelemetryService outside request scope (tests/worker tooling)."""
    settings = get_settings()
    reader = SqlTelemetryReader(session)
    config_repo = SqlConfigPlantaoRepository(session)
    cache = resolve_telemetry_cache(valkey=valkey)
    ttl = (
        cache_ttl_segundos
        if cache_ttl_segundos is not None
        else settings.TELEMETRY_CACHE_TTL_SEGUNDOS
    )
    return TelemetryService(
        reader=reader,
        config_repo=config_repo,
        cache=cache,
        cache_ttl_segundos=ttl,
    )


def get_telemetry_service(
    session: DbSessionDep,
    valkey: ValkeyDep,
) -> TelemetryService:
    """Provide TelemetryService with reader, repository, and Valkey cache wired."""
    return build_telemetry_service_for_session(session=session, valkey=valkey)


TelemetryServiceDep = Annotated[TelemetryService, Depends(get_telemetry_service)]


def build_config_plantao_service_for_session(
    session: AsyncSession,
    valkey: Redis | None = None,
) -> ConfigPlantaoService:
    """Build ConfigPlantaoService outside request scope (tests/worker tooling)."""
    repo = SqlConfigPlantaoRepository(session)
    cache = resolve_telemetry_cache(valkey=valkey)
    return ConfigPlantaoService(
        repo=repo,
        cache=cache,
        session=session,
    )


def get_config_plantao_service(
    session: DbSessionDep,
    valkey: ValkeyDep,
) -> ConfigPlantaoService:
    """Provide ConfigPlantaoService with repository, cache, and session wired."""
    return build_config_plantao_service_for_session(session=session, valkey=valkey)


ConfigPlantaoServiceDep = Annotated[
    ConfigPlantaoService, Depends(get_config_plantao_service)
]
