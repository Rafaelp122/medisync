"""Application services for identity and onboarding."""

from src.modules.identity.application.services.dependente_service import (
    CriarDependenteDTO,
    DependenteDetalheDTO,
    DependenteOutputDTO,
    DependenteService,
)
from src.modules.identity.application.services.onboarding_service import (
    Fase1InputDTO,
    Fase1OutputDTO,
    Fase2InputDTO,
    Fase2OutputDTO,
    OnboardingService,
)
from src.modules.identity.application.services.patient_auth_service import (
    PatientAuthService,
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
    "PatientAuthService",
]
