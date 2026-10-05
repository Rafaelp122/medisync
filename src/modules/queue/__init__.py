"""Queue module exposing domain models, exceptions, application services, and DTOs."""

from src.modules.queue.application import (
    AdquirirProximoPacienteCommand,
    AlocacaoChamadaResult,
    AlocarChamadaCommand,
    AvaliacaoAdmissaoResult,
    AvaliarAdmissaoCommand,
    IngressarFilaComBackpressureCommand,
    IngressarFilaCommand,
    IngressarFilaResult,
    LoggingQueueOverflowNotifier,
    QueueOverflowEvent,
    QueueOverflowNotifierPort,
)
from src.modules.queue.application.services import (
    AlocacaoChamadaService,
    ControleAdmissaoService,
    FilaService,
    avaliar_capacidade_admissao,
)
from src.modules.queue.domain import (
    AdmissaoFilaSuspensaError,
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
    "AdmissaoFilaSuspensaError",
    "AdquirirProximoPacienteCommand",
    "AlocacaoChamadaResult",
    "AlocacaoChamadaService",
    "AlocarChamadaCommand",
    "Atendimento",
    "AtendimentoNaoDisponivelError",
    "AtendimentoNaoEncontradoError",
    "AvaliacaoAdmissaoResult",
    "AvaliarAdmissaoCommand",
    "ControleAdmissaoService",
    "FilaService",
    "FilaVaziaError",
    "IngressarFilaComBackpressureCommand",
    "IngressarFilaCommand",
    "IngressarFilaResult",
    "LoggingQueueOverflowNotifier",
    "MedicoOcupadoError",
    "PrioridadeClinica",
    "QueueOverflowEvent",
    "QueueOverflowNotifierPort",
    "StatusAtendimento",
    "TransicaoEstadoInvalidaError",
    "avaliar_capacidade_admissao",
]
