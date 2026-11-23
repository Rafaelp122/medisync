"""Application Data Transfer Objects for the triage module."""

from dataclasses import dataclass


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
