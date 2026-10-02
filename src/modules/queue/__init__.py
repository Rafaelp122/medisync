"""Queue module exposing domain models, exceptions, application services, and DTOs."""

from src.modules.queue.application import (
    AlocacaoChamadaResult,
    AlocarChamadaCommand,
)
from src.modules.queue.application.services import AlocacaoChamadaService
from src.modules.queue.domain import (
    Atendimento,
    AtendimentoNaoDisponivelError,
    AtendimentoNaoEncontradoError,
    MedicoOcupadoError,
    PrioridadeClinica,
    StatusAtendimento,
    TransicaoEstadoInvalidaError,
)

__all__ = [
    "AlocacaoChamadaResult",
    "AlocacaoChamadaService",
    "AlocarChamadaCommand",
    "Atendimento",
    "AtendimentoNaoDisponivelError",
    "AtendimentoNaoEncontradoError",
    "MedicoOcupadoError",
    "PrioridadeClinica",
    "StatusAtendimento",
    "TransicaoEstadoInvalidaError",
]
