"""Composition Root do módulo scheduling (ADR-001 / ADR-009)."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import DbSessionDep
from src.modules.queue.application.ports.queue_store_port import QueueStorePort
from src.modules.queue.composition import build_fila_service_for_session
from src.modules.scheduling.application.ports.attendance_lookup_port import (
    AttendanceLookupPort,
    AttendanceSnapshot,
)
from src.modules.scheduling.application.ports.scheduling_repository_port import (
    SchedulingRepositoryPort,
)
from src.modules.scheduling.application.services.scheduling_service import (
    SchedulingService,
)
from src.modules.scheduling.infrastructure.adapters.sql_scheduling_repository import (
    SqlSchedulingRepository,
)


class QueueStoreAttendanceLookupAdapter(AttendanceLookupPort):
    """Adapta QueueStorePort.buscar_atendimento para AttendanceLookupPort."""

    def __init__(self, queue_store: QueueStorePort) -> None:
        self._queue_store = queue_store

    async def buscar_atendimento(
        self,
        atendimento_id: UUID,
    ) -> AttendanceSnapshot | None:
        snapshot = await self._queue_store.buscar_atendimento(atendimento_id)
        if snapshot is None:
            return None
        return AttendanceSnapshot(
            id=snapshot.id,
            paciente_id=snapshot.paciente_id,
            medico_id=snapshot.medico_id,
        )


def build_scheduling_service(
    session: AsyncSession,
    repository: SchedulingRepositoryPort | None = None,
    attendance_lookup: AttendanceLookupPort | None = None,
) -> SchedulingService:
    """Constrói SchedulingService fora do escopo de requisição (testes/workers)."""
    resolved_repo = (
        repository if repository is not None else SqlSchedulingRepository(session)
    )
    resolved_lookup: AttendanceLookupPort
    if attendance_lookup is not None:
        resolved_lookup = attendance_lookup
    else:
        queue_store: QueueStorePort = build_fila_service_for_session(session=session)
        resolved_lookup = QueueStoreAttendanceLookupAdapter(queue_store)
    return SchedulingService(
        session=session,
        repository=resolved_repo,
        attendance_lookup=resolved_lookup,
    )


def get_scheduling_service(session: DbSessionDep) -> SchedulingService:
    """Resolve SchedulingService para injeção de dependência FastAPI."""
    return build_scheduling_service(session=session)


SchedulingServiceDep = Annotated[SchedulingService, Depends(get_scheduling_service)]
