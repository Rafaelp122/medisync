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


@runtime_checkable
class AtendimentoReaderPort(Protocol):
    """Reads attendance summaries without touching queue domain models."""

    async def obter_resumo(
        self, atendimento_id: UUID
    ) -> AtendimentoResumoDTO | None: ...
