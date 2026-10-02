"""Queue module exposing domain models, exceptions, application services, and DTOs."""

from src.modules.queue.application import (
    AdquirirProximoPacienteCommand,
    AlocacaoChamadaResult,
    AlocarChamadaCommand,
    IngressarFilaCommand,
    IngressarFilaResult,
)
from src.modules.queue.application.services import (
    AlocacaoChamadaService,
    FilaService,
    calcular_score_fila,
)
from src.modules.queue.domain import (
    Atendimento,
    AtendimentoNaoDisponivelError,
    AtendimentoNaoEncontradoError,
    FilaVaziaError,
    MedicoOcupadoError,
    PrioridadeClinica,
    StatusAtendimento,
    TransicaoEstadoInvalidaError,
)

__all__ = [
    "AdquirirProximoPacienteCommand",
    "AlocacaoChamadaResult",
    "AlocacaoChamadaService",
    "AlocarChamadaCommand",
    "Atendimento",
    "AtendimentoNaoDisponivelError",
    "AtendimentoNaoEncontradoError",
    "FilaService",
    "FilaVaziaError",
    "IngressarFilaCommand",
    "IngressarFilaResult",
    "MedicoOcupadoError",
    "PrioridadeClinica",
    "StatusAtendimento",
    "TransicaoEstadoInvalidaError",
    "calcular_score_fila",
]
