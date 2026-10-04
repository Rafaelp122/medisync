"""Application Data Transfer Objects for the triage module."""

from dataclasses import dataclass

from src.modules.triage.domain.models.triagem import Triagem


@dataclass(frozen=True)
class ResultadoTriagemDTO:
    """Outcome of clinical triage assessment."""

    triagem: Triagem
    prioridade_clinica: int
    tcle_hash: str
    admissao_bloqueada: bool
    alerta_samu_disparado: bool
    instrucao_redirecionamento: str | None = None
