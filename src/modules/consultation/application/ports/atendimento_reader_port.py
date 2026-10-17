"""Port for reading attendance status without importing queue models."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class AtendimentoResumoDTO:
    """Immutable attendance summary for cross-module terminal checks."""

    atendimento_id: UUID
    organizacao_id: int
    medico_id: UUID | None
    status: str
    tcle_hash: str | None
    is_terminal: bool
    paciente_id: UUID | None = None


@runtime_checkable
class AtendimentoReaderPort(Protocol):
    """Reads attendance summaries without touching queue domain models."""

    async def obter_resumo(
        self, atendimento_id: UUID
    ) -> AtendimentoResumoDTO | None: ...

    async def concluir_atendimento(self, atendimento_id: UUID) -> None: ...

    async def atender_chamada(self, atendimento_id: UUID) -> None: ...


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
