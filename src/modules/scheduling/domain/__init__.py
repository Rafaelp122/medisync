"""Camada de domínio do módulo scheduling."""

from src.modules.scheduling.domain.exceptions import (
    AgendamentoNaoEncontradoError,
    SlotIndisponivelError,
    TransicaoAgendamentoInvalidaError,
)
from src.modules.scheduling.domain.models import (
    ESPECIALIDADE_CATALOGO,
    STATUS_AGENDAMENTO_INATIVOS,
    AgendaDisponibilidade,
    Agendamento,
    EspecialidadeAgenda,
    EspecialidadeMetadata,
    StatusAgendamento,
    validar_especialidade_agenda,
)

__all__ = [
    "ESPECIALIDADE_CATALOGO",
    "STATUS_AGENDAMENTO_INATIVOS",
    "AgendaDisponibilidade",
    "Agendamento",
    "AgendamentoNaoEncontradoError",
    "EspecialidadeAgenda",
    "EspecialidadeMetadata",
    "SlotIndisponivelError",
    "StatusAgendamento",
    "TransicaoAgendamentoInvalidaError",
    "validar_especialidade_agenda",
]
