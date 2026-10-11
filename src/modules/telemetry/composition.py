"""Telemetry composition root: concrete adapter wiring (DI Fase 3).

Single place in telemetry module allowed to import infrastructure adapters.
Routers and tests must resolve services via TelemetryServiceDep
and ConfigPlantaoServiceDep.
"""

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import DbSessionDep
from src.core.dependencies import ValkeyDep
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
    ValkeyTelemetryCache,
)


def build_telemetry_service_for_session(
    session: AsyncSession,
    valkey: Redis | None = None,
) -> TelemetryService:
    """Build TelemetryService outside request scope (tests/worker tooling)."""
    reader = SqlTelemetryReader(session)
    config_repo = SqlConfigPlantaoRepository(session)
    cache = ValkeyTelemetryCache(valkey=valkey)
    return TelemetryService(
        reader=reader,
        config_repo=config_repo,
        cache=cache,
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
    cache = ValkeyTelemetryCache(valkey=valkey)
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
