"""Application layer for identity module."""

from src.modules.identity.application.dtos import (
    CriarDependenteInput,
    DependenteDetalheDTO,
    DependenteOutputDTO,
    Fase1Input,
    Fase1OutputDTO,
    Fase2Input,
    Fase2OutputDTO,
)
from src.modules.identity.application.services import (
    DependenteService,
    OnboardingService,
)

__all__ = [
    "CriarDependenteInput",
    "DependenteDetalheDTO",
    "DependenteOutputDTO",
    "DependenteService",
    "Fase1Input",
    "Fase1OutputDTO",
    "Fase2Input",
    "Fase2OutputDTO",
    "OnboardingService",
]
