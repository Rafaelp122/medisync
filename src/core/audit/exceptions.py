"""Domain exceptions for append-only audit events."""

from src.core.errors import DomainError, ValidationError


class AuditoriaImutavelError(DomainError):
    """Raised when an UPDATE or DELETE mutation is attempted on an audit record."""

    status_code: int = 409
    title: str = "Auditoria Imutável — Operação Não Permitida"
    code: str = "AUDITORIA_IMUTAVEL"


class AuditoriaInvalidaError(ValidationError):
    """Raised when audit event payload or attributes violate domain rules."""

    status_code: int = 422
    title: str = "Registro de Auditoria Inválido"
    code: str = "AUDITORIA_INVALIDA"
