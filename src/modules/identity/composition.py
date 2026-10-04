"""Identity composition root: stateless service providers (DI Fase 3)."""

from typing import Annotated

from fastapi import Depends

from src.modules.identity.application.services.dependente_service import (
    DependenteService,
)
from src.modules.identity.application.services.onboarding_service import (
    OnboardingService,
)


def get_onboarding_service() -> OnboardingService:
    """Provide stateless onboarding service instance."""
    return OnboardingService()


OnboardingServiceDep = Annotated[OnboardingService, Depends(get_onboarding_service)]


def get_dependente_service() -> DependenteService:
    """Provide stateless dependent service instance."""
    return DependenteService()


DependenteServiceDep = Annotated[DependenteService, Depends(get_dependente_service)]
