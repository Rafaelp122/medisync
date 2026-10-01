"""Domain exceptions for triage workflows."""

from src.core.errors import DomainError, ValidationError


class EmergenciaCriticaSamuError(DomainError):
    """Raised when critical level 1 emergency is detected, requiring SAMU 192."""

    status_code: int = 422
    title: str = "Emergência Médica Crítica — Acionamento SAMU 192"
    code: str = "EMERGENCIA_CRITICA_SAMU_192"


class TriagemInvalidaError(ValidationError):
    """Raised when clinical triage parameters or inputs violate domain rules."""

    status_code: int = 422
    title: str = "Triagem Clínica Inválida"
    code: str = "TRIAGEM_INVALIDA"
