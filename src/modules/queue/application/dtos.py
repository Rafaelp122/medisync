"""Data Transfer Objects for queue allocation operations."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.modules.queue.domain.models import PrioridadeClinica


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


@dataclass(frozen=True)
class IngressarFilaCommand:
    """Command payload to ingest an apt attendance into the virtual queue."""

    organizacao_id: int
    atendimento_id: UUID
    prioridade_clinica: int | PrioridadeClinica
    data_entrada_fila: datetime | None = None


@dataclass(frozen=True)
class IngressarFilaResult:
    """Immutable result of queue ingestion."""

    atendimento_id: UUID
    organizacao_id: int
    score: int
    posicao: int


@dataclass(frozen=True)
class AdquirirProximoPacienteCommand:
    """Command payload for a doctor to acquire the next patient in queue."""

    organizacao_id: int
    medico_id: UUID
    max_retries: int = 3
    ttl_segundos: int = 45
