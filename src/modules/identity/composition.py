"""Identity composition root: stateless service providers (DI Fase 3)."""

from typing import Annotated

from fastapi import Depends

from src.core.database import DbSessionDep
from src.modules.identity.application.ports.identity_reader_port import (
    IdentityReaderPort,
)
from src.modules.identity.application.services.dependente_service import (
    DependenteService,
)
from src.modules.identity.application.services.onboarding_service import (
    OnboardingService,
)
from src.modules.identity.infrastructure.identity_reader_sql import (
    SqlIdentityReader,
)


def get_onboarding_service(session: DbSessionDep) -> OnboardingService:
    """Provide scoped onboarding service instance."""
    return OnboardingService(session=session)


OnboardingServiceDep = Annotated[OnboardingService, Depends(get_onboarding_service)]


def get_dependente_service(session: DbSessionDep) -> DependenteService:
    """Provide scoped dependent service instance."""
    return DependenteService(session=session)


DependenteServiceDep = Annotated[DependenteService, Depends(get_dependente_service)]


def get_identity_reader(session: DbSessionDep) -> IdentityReaderPort:
    """Provide chainable ORM identity reader port implementation."""
    return SqlIdentityReader(session=session)


IdentityReaderDep = Annotated[IdentityReaderPort, Depends(get_identity_reader)]
