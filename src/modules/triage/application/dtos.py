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

    @property
    def is_emergencia_critica(self) -> bool:
        """Indica se configura emergência com risco à vida (RN04)."""
        return self.prioridade_clinica == 1 or self.alerta_samu_disparado


@dataclass(frozen=True)
class ResultadoTriagemDTO(TriageRiskEvaluationDTO):
    """Outcome of clinical triage assessment with optional entity link.

    Inherits from TriageRiskEvaluationDTO to eliminate duplicated rules.
    """

    admissao_bloqueada: bool = False
    triagem_id: UUID | None = None
    triagem: "Triagem | None" = None

    def __post_init__(self) -> None:
        if self.is_emergencia_critica and not self.admissao_bloqueada:
            object.__setattr__(self, "admissao_bloqueada", True)

    @classmethod
    def from_evaluation(
        cls,
        eval_dto: TriageRiskEvaluationDTO,
        *,
        admissao_bloqueada: bool | None = None,
        triagem_id: UUID | None = None,
        triagem: "Triagem | None" = None,
    ) -> "ResultadoTriagemDTO":
        """Factory aligning ResultadoTriagemDTO with TriageRiskEvaluationDTO."""
        return cls(
            prioridade_clinica=eval_dto.prioridade_clinica,
            tcle_hash=eval_dto.tcle_hash,
            alerta_samu_disparado=eval_dto.alerta_samu_disparado,
            instrucao_redirecionamento=eval_dto.instrucao_redirecionamento,
            admissao_bloqueada=(
                admissao_bloqueada
                if admissao_bloqueada is not None
                else eval_dto.is_emergencia_critica
            ),
            triagem_id=triagem_id,
            triagem=triagem,
        )
