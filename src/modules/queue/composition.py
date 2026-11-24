"""Queue composition root: concrete adapter wiring (DI Fase 3).

Single place in queue module allowed to import infrastructure adapters.
Services and tests must resolve queue operations via FilaServiceDep and builders.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from arq.connections import ArqRedis
from fastapi import Depends
from redis.asyncio import ConnectionPool, Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import AuditTrailPort, SqlAuditTrailAdapter
from src.core.config import get_settings
from src.core.database import DbSessionDep, get_session_factory
from src.core.valkey import ValkeyDep, get_arq_pool, get_valkey_pool
from src.modules.consultation.application.realtime_channels import (
    channel_doctor_calls,
)
from src.modules.queue.application.ports.notification_port import NotificationPort
from src.modules.queue.application.ports.queue_engine_port import QueueEnginePort
from src.modules.queue.application.ports.shift_policy_reader_port import (
    ShiftPolicyDTO,
    ShiftPolicyReaderPort,
)
from src.modules.queue.application.ports.triage_port import TriagePort
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.controle_admissao_service import (
    ControleAdmissaoService,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.infrastructure.active_attendance_reader_sql import (
    SqlActiveAttendanceReader,
)
from src.modules.queue.infrastructure.attendance_snapshot_reader_sql import (
    SqlAttendanceSnapshotReader,
)
from src.modules.queue.infrastructure.lua_loader import get_lua_script_manager
from src.modules.queue.infrastructure.notifications import (
    LoggingNotificationAdapter,
    NotificationRateLimiter,
    RateLimitedNotificationAdapter,
)
from src.modules.queue.infrastructure.valkey_queue_engine import ValkeyQueueEngine
from src.modules.telemetry.composition import ler_politica_plantao_snapshot
from src.modules.triage.composition import (
    TriageServiceDep,
    build_triage_service_for_session,
)

logger = logging.getLogger("medisync.queue.composition")


class TelemetryShiftPolicyReaderAdapter(ShiftPolicyReaderPort):
    """Cross-module reader adapting telemetry shift config into ShiftPolicyDTO."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obter_politica_atual(self) -> ShiftPolicyDTO:
        """Read active shift policy from telemetry without mutating DB."""
        snapshot = await ler_politica_plantao_snapshot(self._session)
        return ShiftPolicyDTO(
            alpha_backpressure=snapshot.alpha_backpressure,
            cota_diaria_maxima=snapshot.cota_diaria_maxima,
            tma_padrao_segundos=snapshot.tma_padrao_segundos,
            tempo_tolerancia_ring_segundos=snapshot.tempo_tolerancia_ring_segundos,
        )


def build_queue_engine(valkey: Redis | None = None) -> ValkeyQueueEngine:
    """Build deep Valkey queue engine with Lua script manager and Pub/Sub channel fn."""
    client = valkey if valkey is not None else Redis(connection_pool=get_valkey_pool())
    return ValkeyQueueEngine(
        valkey=client,
        lua_manager=get_lua_script_manager(),
        doctor_channel_fn=channel_doctor_calls,
    )


def build_doctor_presence_engine(valkey: Redis | None = None) -> QueueEnginePort:
    """Expose QueueEnginePort for cross-module doctor shift presence hooks (auth/WS)."""
    return build_queue_engine(valkey=valkey)


def get_notification_rate_limiter(
    valkey: Redis | None = None,
) -> NotificationRateLimiter:
    """Instancia o rate limiter de notificações a partir das variáveis de ambiente.

    Regras: ADR-009 e docs/reference/environment/variables.md.
    """
    settings = get_settings()
    return NotificationRateLimiter(
        valkey_client=valkey,
        capacity=settings.NOTIFICATION_RATE_LIMIT_CAPACITY,
        refill_rate_per_second=settings.NOTIFICATION_RATE_LIMIT_REFILL_RATE,
        ttl_seconds=settings.NOTIFICATION_RATE_LIMIT_TTL_SECONDS,
    )


def get_notification_adapter(valkey: Redis | None = None) -> NotificationPort | None:
    """Resolve o adaptador de notificações decorado com rate limiting por chamada.

    Regras: ADR-001, ADR-009 e docs/reference/environment/variables.md.
    """
    settings = get_settings()
    if settings.NOTIFICATION_PROVIDER == "noop":
        return None
    delegate = LoggingNotificationAdapter()
    rate_limiter = get_notification_rate_limiter(valkey=valkey)
    return RateLimitedNotificationAdapter(delegate=delegate, rate_limiter=rate_limiter)


async def on_startup(pool: ConnectionPool | None = None) -> None:
    """Preload Valkey Lua scripts on application startup (Lifespan hook)."""
    target_pool = pool or get_valkey_pool()
    client = Redis(connection_pool=target_pool)
    try:
        script_manager = get_lua_script_manager()
        loaded = await script_manager.preload_scripts(client)
        logger.info(
            "Preloaded %d Valkey Lua scripts: %s", len(loaded), list(loaded.keys())
        )
    finally:
        await client.aclose()


async def get_arq_pool_dep() -> ArqRedis | None:
    """Provide ArqRedis pool dependency, or None if Valkey/ARQ is unavailable."""
    try:
        return await get_arq_pool()
    except Exception as exc:
        logger.warning("ArqRedis pool connection unavailable in request scope: %s", exc)
        return None


ArqPoolDep = Annotated[ArqRedis | None, Depends(get_arq_pool_dep)]


def build_alocacao_service_for_session(
    valkey: Redis,
    session: AsyncSession,
    arq_pool: ArqRedis | None = None,
    audit_trail: AuditTrailPort | None = None,
    queue_engine: QueueEnginePort | None = None,
) -> AlocacaoChamadaService:
    """Build allocation service outside request scope (tests/worker tooling)."""
    resolved_audit: AuditTrailPort = audit_trail or SqlAuditTrailAdapter(session)
    resolved_engine: QueueEnginePort = queue_engine or build_queue_engine(valkey=valkey)
    return AlocacaoChamadaService(
        queue_engine=resolved_engine,
        db_session=session,
        arq_pool=arq_pool,
        notification_adapter=get_notification_adapter(valkey=valkey),
        audit_trail=resolved_audit,
    )


def build_fila_service_for_session(
    session: AsyncSession,
    valkey: Redis | None = None,
    triage_port: TriagePort | None = None,
    arq_pool: ArqRedis | None = None,
    audit_trail: AuditTrailPort | None = None,
    queue_engine: QueueEnginePort | None = None,
    shift_policy_reader: ShiftPolicyReaderPort | None = None,
) -> FilaService:
    """Build queue service outside request scope (tests/worker tooling)."""
    client = valkey if valkey is not None else Redis(connection_pool=get_valkey_pool())
    resolved_engine: QueueEnginePort = queue_engine or build_queue_engine(valkey=client)
    resolved_triage: TriagePort = triage_port or build_triage_service_for_session(
        session=session
    )
    resolved_audit: AuditTrailPort = audit_trail or SqlAuditTrailAdapter(session)
    resolved_policy: ShiftPolicyReaderPort = (
        shift_policy_reader or TelemetryShiftPolicyReaderAdapter(session=session)
    )
    return FilaService(
        queue_engine=resolved_engine,
        db_session=session,
        alocacao_service=build_alocacao_service_for_session(
            client,
            session,
            arq_pool=arq_pool,
            audit_trail=resolved_audit,
            queue_engine=resolved_engine,
        ),
        controle_admissao=ControleAdmissaoService(queue_engine=resolved_engine),
        triage_port=resolved_triage,
        shift_policy_reader=resolved_policy,
        arq_pool=arq_pool,
        audit_trail=resolved_audit,
    )


def get_fila_service(
    valkey: ValkeyDep,
    session: DbSessionDep,
    triage_service: TriageServiceDep,
    arq_pool: ArqPoolDep,
) -> FilaService:
    """Build queue service with allocation, admission, and shift policy wired."""
    return build_fila_service_for_session(
        session=session,
        valkey=valkey,
        triage_port=triage_service,
        arq_pool=arq_pool,
    )


FilaServiceDep = Annotated[FilaService, Depends(get_fila_service)]


async def default_verificar_posse_paciente_fila(
    atendimento_id: UUID,
    paciente_id: UUID,
) -> bool:
    """Verifica se o atendimento pertence ao paciente com sessão efêmera (Issue #42)."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        queue_store = build_fila_service_for_session(session=session)
        snapshot = await queue_store.buscar_atendimento(atendimento_id)
        if snapshot is None:
            return False
        return snapshot.paciente_id == paciente_id


PatientQueueOwnershipChecker = Callable[[UUID, UUID], Awaitable[bool]]


def get_patient_queue_ownership_checker() -> PatientQueueOwnershipChecker:
    """Provide the default ownership checker for patient queue WebSockets."""
    return default_verificar_posse_paciente_fila


PatientQueueOwnershipCheckerDep = Annotated[
    PatientQueueOwnershipChecker, Depends(get_patient_queue_ownership_checker)
]


def build_active_attendance_reader_for_session(
    session: AsyncSession,
) -> SqlActiveAttendanceReader:
    """Instancia leitor SQL de atendimento ativo para módulos consumidores (auth).

    Regras: ADR-001 e docs/user-stories/US-02-autenticacao-passwordless-otp.md.
    """
    return SqlActiveAttendanceReader(session=session)


def build_attendance_lookup_reader(
    session: AsyncSession,
) -> SqlAttendanceSnapshotReader:
    """Instancia leitor SQL leve de atendimentos para módulos consumidores (scheduling).

    Zero dependência de Valkey, LuaScriptManager ou TriageService.
    Regras: ADR-001 e docs/explanation/domains/scheduling-domain.md.
    """
    return SqlAttendanceSnapshotReader(session=session)
