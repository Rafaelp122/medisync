"""Data Transfer Objects and application protocols for queue operations."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from src.modules.queue.domain.models import PrioridadeClinica


@dataclass(frozen=True)
class AlocarChamadaCommand:
    """Command payload to allocate a patient call to a doctor."""

    medico_id: UUID
    atendimento_id: UUID
    ttl_segundos: int = 45
    telefone_paciente: str | None = None


@dataclass(frozen=True)
class AlocacaoChamadaResult:
    """Immutable result of an atomic call allocation."""

    atendimento_id: UUID
    medico_id: UUID
    status: str
    chamada_iniciada_em: datetime
    ttl_segundos: int
    paciente_id: UUID | None = None
    prioridade_clinica: int | None = None
    alocado: bool = True
    mensagem: str = "Paciente alocado com sucesso para chamada."


@dataclass(frozen=True)
class IngressarFilaCommand:
    """Command payload to ingest an apt attendance into the virtual queue."""

    atendimento_id: UUID
    prioridade_clinica: int | PrioridadeClinica
    data_entrada_fila: datetime | None = None


@dataclass(frozen=True)
class IngressarFilaResult:
    """Immutable result of queue ingestion."""

    atendimento_id: UUID
    score: int
    posicao: int


@dataclass(frozen=True)
class AdquirirProximoPacienteCommand:
    """Command payload for a doctor to acquire the next patient in queue."""

    medico_id: UUID
    max_scan: int = 50
    ttl_segundos: int | None = None


@dataclass(frozen=True)
class AvaliarAdmissaoCommand:
    """Command payload to evaluate stochastic admission capacity (RN05)."""

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
class AdmissaoAtendimentoCommand:
    """Command payload for unified clinical intake and triage admission."""

    paciente_id: UUID
    queixa_principal: str
    sintomas: list[str]
    escala_dor: int = 0
    tcle_texto: str = ""
    tcle_hash: str | None = None
    tempo_restante_segundos: float = 14400.0
    tma_estimado_segundos: int | None = None
    alpha_margem: float | None = None
    cota_diaria_maxima: int | None = None
    cpf: str | None = None
    cns: str | None = None
    ip_origem: str | None = None


@dataclass(frozen=True)
class AdmissaoAtendimentoResult:
    """Immutable result of patient clinical admission and triage."""

    atendimento_id: UUID
    triagem_id: UUID
    paciente_id: UUID
    status_atendimento: str
    prioridade_clinica: int
    alerta_samu_disparado: bool
    instrucoes: str | None = None
    tcle_hash: str | None = None


@dataclass(frozen=True)
class PosicaoFilaResult:
    """Immutable projection of patient position and wait estimate in queue."""

    atendimento_id: UUID
    status: str
    posicao: int | None
    total_aguardando: int
    tempo_estimado_segundos: int | None
    prioridade_clinica: int = 5
    chamada_iniciada_em: datetime | None = None
    ttl_segundos: int | None = None


@dataclass(frozen=True)
class CancelarAtendimentoResult:
    """Immutable result of patient voluntary cancellation."""

    atendimento_id: UUID
    status: str
    cancelado_em: datetime
    motivo: str | None = None


@runtime_checkable
class PioraClinicaInput(Protocol):
    """Input protocol for clinical deterioration reassessment avoiding DTO mirroring."""

    @property
    def atendimento_id(self) -> UUID:
        """Attendance identifier."""
        ...

    @property
    def novos_sintomas(self) -> Sequence[str]:
        """Reported new or worsening symptoms."""
        ...

    @property
    def escala_dor(self) -> int:
        """Updated pain scale from 0 to 10."""
        ...

    @property
    def queixa_adicional(self) -> str:
        """Additional clinical description."""
        ...


@dataclass(frozen=True)
class PioraClinicaResult:
    """Immutable result of clinical deterioration evaluation."""

    atendimento_id: UUID
    prioridade_clinica: int
    alerta_samu_disparado: bool
    redirecionado_emergencia: bool
    nova_posicao: int | None
    instrucoes: str | None = None
    status_atendimento: str | None = None


@dataclass(frozen=True)
class RegularizacaoFilaCommand:
    """Comando para regularização de atendimento retido ou contingência assistencial."""

    atendimento_id: UUID
    motivo: str
    tipo_contingencia: str = "CONTINGENCIA_ASSISTENCIAL"


@dataclass(frozen=True)
class RegularizacaoFilaResult:
    """Resultado da regularização ou promoção por contingência na fila."""

    atendimento_id: UUID
    promovido: bool
    status: str
    score: int
    tipo_contingencia: str
    mensagem: str


__all__ = [
    "AdmissaoAtendimentoCommand",
    "AdmissaoAtendimentoResult",
    "AdquirirProximoPacienteCommand",
    "AlocacaoChamadaResult",
    "AlocarChamadaCommand",
    "AvaliacaoAdmissaoResult",
    "AvaliarAdmissaoCommand",
    "CancelarAtendimentoResult",
    "IngressarFilaCommand",
    "IngressarFilaResult",
    "PioraClinicaInput",
    "PioraClinicaResult",
    "PosicaoFilaResult",
    "RegularizacaoFilaCommand",
    "RegularizacaoFilaResult",
]
