"""Port for reading attendance status without importing queue models."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class AtendimentoResumoDTO:
    """Immutable attendance summary for cross-module terminal checks."""

    atendimento_id: UUID
    medico_id: UUID | None
    status: str
    tcle_hash: str | None
    is_terminal: bool
    paciente_id: UUID | None = None
    chamada_iniciada_em: datetime | None = None
    criado_em: datetime | None = None
    exige_liveness_controle_especial: bool = True


@dataclass(frozen=True)
class AtendimentoHistoricoDTO:
    """Immutable patient attendance history entry from queue-owned tables."""

    atendimento_id: UUID
    paciente_id: UUID
    status: str
    prioridade_clinica: int
    criado_em: datetime
    finalizado_em: datetime | None = None
    medico_id: UUID | None = None
    queixa_principal: str | None = None


@runtime_checkable
class AtendimentoReaderPort(Protocol):
    """Reads attendance summaries without touching queue domain models."""

    async def obter_resumo(
        self, atendimento_id: UUID
    ) -> AtendimentoResumoDTO | None: ...

    async def concluir_atendimento(self, atendimento_id: UUID) -> None: ...

    async def atender_chamada(self, atendimento_id: UUID) -> None: ...


@runtime_checkable
class HistoricoAtendimentoReaderPort(Protocol):
    """Reads patient attendance history without touching queue domain models."""

    async def listar_historico_paciente(
        self,
        paciente_id: UUID,
    ) -> list[AtendimentoHistoricoDTO]: ...


async def is_atendimento_terminal(
    reader: AtendimentoReaderPort | None,
    atendimento_id: UUID,
) -> bool:
    """Return True when queue-owned attendance reached terminal status."""
    if reader is None:
        return False
    try:
        resumo = await reader.obter_resumo(atendimento_id)
    except Exception:
        return False
    return bool(resumo is not None and resumo.is_terminal)
