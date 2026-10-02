"""Domain exceptions for queue and attendance workflows."""

from src.core.errors import ConflictError, DomainError, NotFoundError


class TransicaoEstadoInvalidaError(DomainError):
    """Raised when an invalid state machine transition is attempted."""

    status_code: int = 409
    title: str = "Transição de Estado Inválida"
    code: str = "TRANSICAO_ESTADO_INVALIDA"


class MedicoOcupadoError(ConflictError):
    """Raised when doctor already holds an active call or consultation lock (RN02)."""

    status_code: int = 409
    title: str = "Médico Ocupado"
    code: str = "MEDICO_OCUPADO"


class AtendimentoNaoDisponivelError(ConflictError):
    """Raised when attendance was concurrently snatched or is not in queue."""

    status_code: int = 409
    title: str = "Atendimento Não Disponível"
    code: str = "ATENDIMENTO_NAO_DISPONIVEL"


class AtendimentoNaoEncontradoError(NotFoundError):
    """Raised when attendance aggregate is not found in database."""

    status_code: int = 404
    title: str = "Atendimento Não Encontrado"
    code: str = "ATENDIMENTO_NAO_ENCONTRADO"
