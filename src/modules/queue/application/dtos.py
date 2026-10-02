"""Data Transfer Objects for queue allocation operations."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class AlocarChamadaCommand:
    """Command payload to allocate a patient call to a doctor."""

    organizacao_id: int
    medico_id: UUID
    atendimento_id: UUID
    ttl_segundos: int = 45


@dataclass(frozen=True)
class AlocacaoChamadaResult:
    """Immutable result of an atomic call allocation."""

    atendimento_id: UUID
    medico_id: UUID
    status: str
    chamada_iniciada_em: datetime
    ttl_segundos: int
