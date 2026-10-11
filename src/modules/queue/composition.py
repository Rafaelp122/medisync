"""Queue composition root: concrete adapter wiring (DI Fase 3).

Single place in queue module allowed to import infrastructure adapters.
Services and tests must resolve allocation via get_alocacao_service.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import DbSessionDep
from src.core.notifications import LoggingNotificationAdapter
from src.core.valkey import get_valkey_client, get_valkey_pool
from src.modules.queue.application.ports.allocation_port import AllocationPort
from src.modules.queue.application.ports.notification_port import NotificationPort
from src.modules.queue.application.ports.queue_store_port import QueueStorePort
from src.modules.queue.application.services.admissao_service import (
    AdmissaoAtendimentoService,
)
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.controle_admissao_service import (
    ControleAdmissaoService,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.infrastructure.lua_loader import get_lua_script_manager

ValkeyDep = Annotated[Redis, Depends(get_valkey_client)]


def get_lua_manager() -> AllocationPort:
    """Provide singleton Lua script manager satisfying the application port."""
    return get_lua_script_manager()


def get_notification_adapter() -> NotificationPort | None:
    """Provide notification adapter per NOTIFICATION_PROVIDER (None for noop)."""
    settings = get_settings()
    if settings.NOTIFICATION_PROVIDER == "noop":
        return None
    return LoggingNotificationAdapter()


def build_alocacao_service_for_session(
    valkey: Redis, session: AsyncSession
) -> AlocacaoChamadaService:
    """Build allocation service outside request scope (tests/worker tooling)."""
    return AlocacaoChamadaService(
        valkey=valkey,
        db_session=session,
        lua_manager=get_lua_manager(),
        notification_adapter=get_notification_adapter(),
    )


def get_alocacao_service(
    valkey: ValkeyDep, session: DbSessionDep
) -> AlocacaoChamadaService:
    """Build allocation service with mandatory Lua port wired."""
    return build_alocacao_service_for_session(valkey, session)


AlocacaoServiceDep = Annotated[AlocacaoChamadaService, Depends(get_alocacao_service)]


def get_controle_admissao(valkey: ValkeyDep) -> ControleAdmissaoService:
    """Provide admission control service bound to Valkey."""
    return ControleAdmissaoService(valkey=valkey)


def build_fila_service_for_session(
    session: AsyncSession,
    valkey: Redis | None = None,
) -> FilaService:
    """Build queue service outside request scope (tests/worker tooling)."""
    client = valkey if valkey is not None else Redis(connection_pool=get_valkey_pool())
    return FilaService(
        valkey=client,
        db_session=session,
        alocacao_service=build_alocacao_service_for_session(client, session),
        controle_admissao=ControleAdmissaoService(valkey=client),
    )


def get_fila_service(valkey: ValkeyDep, session: DbSessionDep) -> FilaService:
    """Build queue service with allocation and admission control wired."""
    return build_fila_service_for_session(session=session, valkey=valkey)


FilaServiceDep = Annotated[FilaService, Depends(get_fila_service)]


def get_queue_store(valkey: ValkeyDep, session: DbSessionDep) -> QueueStorePort:
    """Provide queue store satisfying QueueStorePort."""
    return get_fila_service(valkey=valkey, session=session)


QueueStoreDep = Annotated[QueueStorePort, Depends(get_queue_store)]


def get_admissao_service(
    session: DbSessionDep,
    fila_service: FilaServiceDep,
) -> AdmissaoAtendimentoService:
    """Provide clinical admission and triage service."""
    return AdmissaoAtendimentoService(
        session=session,
        fila_service=fila_service,
    )


AdmissaoServiceDep = Annotated[
    AdmissaoAtendimentoService, Depends(get_admissao_service)
]


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
