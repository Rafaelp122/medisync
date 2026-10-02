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


@dataclass(frozen=True)
class AvaliarAdmissaoCommand:
    """Command payload to evaluate stochastic admission capacity (RN05)."""

    organizacao_id: int
    medicos_ativos: int
    tempo_restante_segundos: float
    pacientes_aguardando: int | None = None
    total_admissoes_hoje: int = 0
    tma_estimado_segundos: int = 600
    alpha_margem: float = 1.25
    cota_diaria_maxima: int | None = 300


@dataclass(frozen=True)
class AvaliacaoAdmissaoResult:
    """Immutable result of stochastic admission evaluation."""

    admissao_permitida: bool
    motivo_bloqueio: str | None
    carga_estimada_segundos: float
    tempo_restante_segundos: float
    pacientes_aguardando: int
    medicos_ativos: int
    alpha_utilizado: float
    mensagem_explicativa: str


@dataclass(frozen=True)
class IngressarFilaComBackpressureCommand:
    """Command payload to ingest attendance with stochastic backpressure check."""

    organizacao_id: int
    atendimento_id: UUID
    prioridade_clinica: int | PrioridadeClinica
    medicos_ativos: int
    tempo_restante_segundos: float
    tma_estimado_segundos: int = 600
    alpha_margem: float = 1.25
    cota_diaria_maxima: int | None = 300
    total_admissoes_hoje: int = 0
    data_entrada_fila: datetime | None = None
