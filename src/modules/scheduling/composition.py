"""Composition Root do módulo scheduling (ADR-001 / ADR-009)."""

from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import DbSessionDep
from src.modules.queue.application.ports.queue_store_port import (
    AtendimentoSnapshotDTO,
)
from src.modules.queue.composition import build_attendance_lookup_reader
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


class _AttendanceSnapshotReaderPort(Protocol):
    async def buscar_atendimento(
        self,
        atendimento_id: UUID,
    ) -> AtendimentoSnapshotDTO | None: ...


class QueueAttendanceSnapshotLookupAdapter(AttendanceLookupPort):
    """Adapta leitor SQL read-only leve de queue para AttendanceLookupPort."""

    def __init__(self, reader: _AttendanceSnapshotReaderPort) -> None:
        self._reader = reader

    async def buscar_atendimento(
        self,
        atendimento_id: UUID,
    ) -> AttendanceSnapshot | None:
        snapshot = await self._reader.buscar_atendimento(atendimento_id)
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
        reader = build_attendance_lookup_reader(session=session)
        resolved_lookup = QueueAttendanceSnapshotLookupAdapter(reader)
    return SchedulingService(
        session=session,
        repository=resolved_repo,
        attendance_lookup=resolved_lookup,
    )


def get_scheduling_service(session: DbSessionDep) -> SchedulingService:
    """Resolve SchedulingService para injeção de dependência FastAPI."""
    return build_scheduling_service(session=session)


SchedulingServiceDep = Annotated[SchedulingService, Depends(get_scheduling_service)]
