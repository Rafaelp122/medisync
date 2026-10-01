"""Domain exceptions for queue and attendance workflows."""

from src.core.errors import DomainError


class TransicaoEstadoInvalidaError(DomainError):
    """Raised when an invalid state machine transition is attempted."""

    status_code: int = 409
    title: str = "Transição de Estado Inválida"
    code: str = "TRANSICAO_ESTADO_INVALIDA"
