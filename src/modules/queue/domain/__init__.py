"""Queue domain layer."""

from src.modules.queue.domain.exceptions import (
    AdmissaoFilaSuspensaError,
    AtendimentoNaoDisponivelError,
    AtendimentoNaoEncontradoError,
    FilaVaziaError,
    MedicoOcupadoError,
    TransicaoEstadoInvalidaError,
)
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)

__all__ = [
    "AdmissaoFilaSuspensaError",
    "Atendimento",
    "AtendimentoNaoDisponivelError",
    "AtendimentoNaoEncontradoError",
    "FilaVaziaError",
    "MedicoOcupadoError",
    "PrioridadeClinica",
    "StatusAtendimento",
    "TransicaoEstadoInvalidaError",
]
