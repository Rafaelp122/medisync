"""Queue composition root: concrete adapter wiring (DI Fase 3).

Single place in queue module allowed to import infrastructure adapters.
Services and tests must resolve allocation via get_alocacao_service.
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
from src.core.database import DbSessionDep
from src.core.dependencies import ValkeyDep
from src.core.realtime import publish_realtime_event
from src.core.valkey import get_arq_pool, get_valkey_pool
from src.modules.consultation.application.realtime_channels import (
    channel_doctor_calls,
)
from src.modules.queue.application.ports.allocation_port import AllocationPort
from src.modules.queue.application.ports.doctor_call_notifier_port import (
    DoctorCallNotifierPort,
)
from src.modules.queue.application.ports.notification_port import NotificationPort
from src.modules.queue.application.ports.triage_port import TriagePort
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.controle_admissao_service import (
    ControleAdmissaoService,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.infrastructure.lua_loader import get_lua_script_manager
from src.modules.queue.infrastructure.notifications import (
    LoggingNotificationAdapter,
    NotificationRateLimiter,
    RateLimitedNotificationAdapter,
)
from src.modules.triage.composition import (
    TriageServiceDep,
    build_triage_service_for_session,
)


def get_lua_manager() -> AllocationPort:
    """Provide singleton Lua script manager satisfying the application port."""
    return get_lua_script_manager()


def get_notification_rate_limiter(
    valkey: Redis | None = None,
) -> NotificationRateLimiter:
    """Instancia o rate limiter de notificações a partir das variáveis de ambiente.

    Regras: ADR-009 e docs/reference/environment/variables.md.
    Protege provedores contra picos de tráfego e custos por telefone.
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
    Retorna None quando configurado como noop ou decora o logger com token bucket.
    """
    settings = get_settings()
    if settings.NOTIFICATION_PROVIDER == "noop":
        return None
    delegate = LoggingNotificationAdapter()
    rate_limiter = get_notification_rate_limiter(valkey=valkey)
    return RateLimitedNotificationAdapter(delegate=delegate, rate_limiter=rate_limiter)


logger = logging.getLogger("medisync.queue.composition")


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


class ValkeyDoctorCallNotifier(DoctorCallNotifierPort):
    """Adaptador concreto para notificação realtime via Valkey Pub/Sub.

    Regras: ADR-001, ADR-002 e docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md.
    """

    def __init__(self, valkey: Redis) -> None:
        self._valkey = valkey

    async def notificar_chamada_iniciada(
        self,
        medico_id: UUID,
        atendimento_id: UUID,
        ttl_segundos: int,
        chamada_iniciada_em: str,
    ) -> None:
        """Dispara evento INCOMING_CALL para o canal Pub/Sub do médico."""
        await publish_realtime_event(
            valkey=self._valkey,
            channel=channel_doctor_calls(medico_id),
            payload={
                "event": "INCOMING_CALL",
                "atendimento_id": str(atendimento_id),
                "medico_id": str(medico_id),
                "ttl_segundos": ttl_segundos,
                "chamada_iniciada_em": chamada_iniciada_em,
            },
        )


def build_alocacao_service_for_session(
    valkey: Redis,
    session: AsyncSession,
    arq_pool: ArqRedis | None = None,
    doctor_notifier: DoctorCallNotifierPort | None = None,
    audit_trail: AuditTrailPort | None = None,
) -> AlocacaoChamadaService:
    """Build allocation service outside request scope (tests/worker tooling)."""
    notifier = doctor_notifier or ValkeyDoctorCallNotifier(valkey=valkey)
    resolved_audit: AuditTrailPort = audit_trail or SqlAuditTrailAdapter(session)
    return AlocacaoChamadaService(
        valkey=valkey,
        db_session=session,
        lua_manager=get_lua_manager(),
        arq_pool=arq_pool,
        notification_adapter=get_notification_adapter(valkey=valkey),
        doctor_notifier=notifier,
        audit_trail=resolved_audit,
    )


def get_alocacao_service(
    valkey: ValkeyDep,
    session: DbSessionDep,
    arq_pool: ArqPoolDep = None,
) -> AlocacaoChamadaService:
    """Build allocation service with mandatory Lua and ARQ pool wired."""
    return build_alocacao_service_for_session(valkey, session, arq_pool=arq_pool)


def build_fila_service_for_session(
    session: AsyncSession,
    valkey: Redis | None = None,
    triage_port: TriagePort | None = None,
    arq_pool: ArqRedis | None = None,
    audit_trail: AuditTrailPort | None = None,
) -> FilaService:
    """Build queue service outside request scope (tests/worker tooling)."""
    client = valkey if valkey is not None else Redis(connection_pool=get_valkey_pool())
    resolved_triage: TriagePort = triage_port or build_triage_service_for_session(
        session=session
    )
    resolved_audit: AuditTrailPort = audit_trail or SqlAuditTrailAdapter(session)
    return FilaService(
        valkey=client,
        db_session=session,
        alocacao_service=build_alocacao_service_for_session(
            client, session, arq_pool=arq_pool, audit_trail=resolved_audit
        ),
        controle_admissao=ControleAdmissaoService(valkey=client),
        triage_port=resolved_triage,
        arq_pool=arq_pool,
        audit_trail=resolved_audit,
    )


def get_fila_service(
    valkey: ValkeyDep,
    session: DbSessionDep,
    triage_service: TriageServiceDep,
    arq_pool: ArqPoolDep,
) -> FilaService:
    """Build queue service with allocation and admission control wired."""
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
    """Verifica se o atendimento pertence ao paciente com sessão efêmera (Issue #42).

    Abre uma sessão isolada pontual que é fechada imediatamente, evitando
    reter conexões do pool de banco durante a vida do streaming WebSocket.
    """
    from src.core.database import async_session_factory

    async with async_session_factory() as session:
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
