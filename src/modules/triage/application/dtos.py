"""Application Data Transfer Objects for the triage module."""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.modules.triage.domain.models.triagem import Triagem


@dataclass(frozen=True)
class TriageRiskEvaluationDTO:
    """Immutable clinical risk evaluation outcome."""

    prioridade_clinica: int
    tcle_hash: str
    alerta_samu_disparado: bool = False
    instrucao_redirecionamento: str | None = None


@dataclass(frozen=True)
class ResultadoTriagemDTO:
    """Outcome of clinical triage assessment."""

    triagem_id: UUID | None
    prioridade_clinica: int
    tcle_hash: str
    admissao_bloqueada: bool
    alerta_samu_disparado: bool
    instrucao_redirecionamento: str | None = None
    triagem: "Triagem | None" = None
