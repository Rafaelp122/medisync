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
    paciente_id: UUID
    medico_id: UUID | None
    status: str
    prioridade_clinica: int
    tcle_hash: str | None
    data_entrada_fila: datetime | None
    criado_em: datetime
    is_terminal: bool
    chamada_iniciada_em: datetime | None = None


@dataclass(frozen=True)
class AtendimentoHistoricoQueueDTO:
    """Immutable attendance history entry for cross-module history readers."""

    atendimento_id: UUID
    paciente_id: UUID
    status: str
    prioridade_clinica: int
    criado_em: datetime
    finalizado_em: datetime | None = None
    medico_id: UUID | None = None
    queixa_principal: str | None = None


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
        atendimento_id: UUID,
        codigo_autorizacao: str | None = None,
    ) -> AdmissaoAptoResult:
        """Promote attendance to APTO_PARA_CHAMADA in DB and ingest into Valkey queue.

        Returns AdmissaoAptoResult.
        """
        ...

    async def resolver_ring_timeout(
        self,
        atendimento_id: UUID,
        medico_id: UUID,
        notifier: PacienteAusenteNotifierPort | None = None,
    ) -> str:
        """Resolve deterministic 45s ring timeout (no-show or preserve active).

        Returns the resolution action name ('no_show_recorded',
        'active_consultation_preserved', 'already_finalized').
        """
        ...

    async def atender_chamada(
        self,
        atendimento_id: UUID,
    ) -> None:
        """Transition attendance in CHAMANDO_PACIENTE to EM_ATENDIMENTO,

        commit DB, and promote doctor ring lock to active consultation (7200s).
        Idempotent if already in EM_ATENDIMENTO.
        """
        ...

    async def concluir_atendimento(
        self,
        atendimento_id: UUID,
        *,
        auto_commit: bool = True,
    ) -> UUID | None:
        """Transition attendance in EM_ATENDIMENTO to CONCLUIDO and persist.

        When ``auto_commit=False``, flushes DB changes without committing so the caller
        (e.g. PEPService.finalizar_consulta) can commit atomically and then
        release ``lock:consulta_ativa:medico:{medico_id}`` via
        ``liberar_consulta_ativa_medico``.
        Returns the assigned ``medico_id`` (if any) for post-commit release.
        """
        ...

    async def liberar_consulta_ativa_medico(self, medico_id: UUID) -> None:
        """Release active consultation lock after atomic commit completes."""
        ...

    async def reconciliar_fila_orfaos(
        self,
        cutoff_em: datetime,
        batch_size: int = 200,
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

    async def listar_historico_paciente(
        self,
        paciente_id: UUID,
    ) -> list[AtendimentoHistoricoQueueDTO]:
        """List patient attendance history entries ordered newest first."""
        ...
