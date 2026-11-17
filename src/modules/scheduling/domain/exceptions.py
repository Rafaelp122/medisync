"""Exceções canônicas de domínio do módulo scheduling."""

from src.core.errors import ConflictError, DomainError, NotFoundError


class TransicaoAgendamentoInvalidaError(DomainError):
    """Lançada quando uma transição de estado de agendamento é inválida.

    Regras: docs/explanation/domains/scheduling-domain.md
    """

    status_code: int = 409
    title: str = "Transição de Agendamento Inválida"
    code: str = "TRANSICAO_AGENDAMENTO_INVALIDA"


class AgendamentoNaoEncontradoError(NotFoundError):
    """Lançada quando o agendamento não existe ou não pertence ao tenant ativo.

    Regras: docs/explanation/domains/scheduling-domain.md
    """

    status_code: int = 404
    title: str = "Agendamento Não Encontrado"
    code: str = "AGENDAMENTO_NAO_ENCONTRADO"


class SlotIndisponivelError(ConflictError):
    """Lançada quando há conflito de horário (double-booking) para o profissional.

    Regras: docs/explanation/domains/scheduling-domain.md
    """

    status_code: int = 409
    title: str = "Slot Indisponível"
    code: str = "SLOT_INDISPONIVEL"
