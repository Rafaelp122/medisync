"""Public port and DTOs for queue storage, state transitions, and coordination."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from src.modules.queue.application.ports.paciente_ausente_notifier import (
    PacienteAusenteNotifierPort,
)


@dataclass(frozen=True)
class AtendimentoSnapshotDTO:
    """Immutable snapshot of attendance state for cross-module readers."""

    id: UUID
    organizacao_id: int
    paciente_id: UUID
    medico_id: UUID | None
    status: str
    prioridade_clinica: int
    tcle_hash: str | None
    data_entrada_fila: datetime | None
    criado_em: datetime
    is_terminal: bool


@dataclass(frozen=True)
class AdmissaoAptoResult:
    """Result of admitting an attendance to APTO status."""

    promovido: bool
    status: str
    score: int


@runtime_checkable
class QueueStorePort(Protocol):
    """Protocol encapsulating queue storage and worker coordination."""

    async def admitir_atendimento_apto(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
    ) -> AdmissaoAptoResult:
        """Promote attendance to APTO_PARA_CHAMADA in DB and ingest into Valkey queue.

        Returns AdmissaoAptoResult.
        """
        ...

    async def resolver_ring_timeout(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
        medico_id: UUID,
        notifier: PacienteAusenteNotifierPort | None = None,
    ) -> str:
        """Resolve deterministic 45s ring timeout (no-show or preserve active).

        Returns the resolution action name ('no_show_recorded',
        'active_consultation_preserved', 'already_finalized').
        """
        ...

    async def concluir_atendimento(
        self,
        atendimento_id: UUID,
    ) -> None:
        """Transition attendance in EM_ATENDIMENTO to CONCLUIDO and persist."""
        ...

    async def reconciliar_fila_orfaos(
        self,
        organizacao_id: int,
        cutoff_em: datetime,
    ) -> tuple[int, list[str]]:
        """Find orphan APTO attendances missing in Valkey and reinject them.

        Returns (scanned_count, reconciled_attendance_ids).
        """
        ...

    async def buscar_atendimento(
        self,
        atendimento_id: UUID,
    ) -> AtendimentoSnapshotDTO | None:
        """Fetch attendance snapshot by ID without leaking ORM model across modules."""
        ...
