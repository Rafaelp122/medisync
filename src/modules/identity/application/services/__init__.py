"""Application services for identity and onboarding."""

from src.modules.identity.application.dtos import (
    CriarDependenteInput,
    DependenteDetalheDTO,
    DependenteOutputDTO,
    Fase1Input,
    Fase1OutputDTO,
    Fase2Input,
    Fase2OutputDTO,
)
from src.modules.identity.application.services.dependente_service import (
    DependenteService,
)
from src.modules.identity.application.services.onboarding_service import (
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
