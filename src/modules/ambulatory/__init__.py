"""Ambulatory module package (ADR-012)."""

from src.modules.ambulatory.application.dtos import (
    BpaProducaoDTO,
    ConsolidarTeleconsultaCommand,
    RequisicaoElegibilidade,
    ResultadoElegibilidade,
)
from src.modules.ambulatory.application.ports import (
    ElegibilidadeFalhaEvent,
    ElegibilidadeNotifierPort,
    EligibilityProviderPort,
    LoggingElegibilidadeNotifier,
)
from src.modules.ambulatory.application.services import ElegibilidadeService
from src.modules.ambulatory.domain.enums import (
    CaraterAtendimento,
    StatusElegibilidade,
    TipoProcedimentoAmbulatorial,
)
from src.modules.ambulatory.infrastructure.adapters import (
    SusEligibilityAdapter,
)

__all__ = [
    "BpaProducaoDTO",
    "CaraterAtendimento",
    "ConsolidarTeleconsultaCommand",
    "ElegibilidadeFalhaEvent",
    "ElegibilidadeNotifierPort",
    "ElegibilidadeService",
    "EligibilityProviderPort",
    "LoggingElegibilidadeNotifier",
    "RequisicaoElegibilidade",
    "ResultadoElegibilidade",
    "StatusElegibilidade",
    "SusEligibilityAdapter",
    "TipoProcedimentoAmbulatorial",
]
