"""Application layer for identity module."""

from src.modules.identity.application.dtos import (
    CriarDependenteDTO,
    DependenteDetalheDTO,
    DependenteOutputDTO,
    Fase1InputDTO,
    Fase1OutputDTO,
    Fase2InputDTO,
    Fase2OutputDTO,
)
from src.modules.identity.application.services import (
    DependenteService,
    OnboardingService,
)

__all__ = [
    "CriarDependenteDTO",
    "DependenteDetalheDTO",
    "DependenteOutputDTO",
    "DependenteService",
    "Fase1InputDTO",
    "Fase1OutputDTO",
    "Fase2InputDTO",
    "Fase2OutputDTO",
    "OnboardingService",
]
