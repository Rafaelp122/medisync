"""Queue domain layer."""

from src.modules.queue.domain.exceptions import (
    AdmissaoFilaSuspensaError,
    AtendimentoNaoDisponivelError,
    AtendimentoNaoEncontradoError,
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
    "MedicoOcupadoError",
    "PrioridadeClinica",
    "StatusAtendimento",
    "TransicaoEstadoInvalidaError",
]
