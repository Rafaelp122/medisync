"""Identity composition root: stateless service providers (DI Fase 3)."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import DbSessionDep
from src.modules.identity.application.ports.identity_reader_port import (
    IdentityReaderPort,
)
from src.modules.identity.application.ports.sms_sender_port import SmsSenderPort
from src.modules.identity.application.services.dependente_service import (
    DependenteService,
)
from src.modules.identity.application.services.onboarding_service import (
    OnboardingService,
)
from src.modules.identity.infrastructure.fake_sms_adapter import FakeSmsSenderAdapter
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


def build_identity_reader_sql_for_session(
    session: AsyncSession,
) -> IdentityReaderPort:
    """Build identity reader outside request scope (tests/worker tooling)."""
    return SqlIdentityReader(session=session)


def get_identity_reader(session: DbSessionDep) -> IdentityReaderPort:
    """Provide chainable ORM identity reader port implementation."""
    return build_identity_reader_sql_for_session(session=session)


IdentityReaderDep = Annotated[IdentityReaderPort, Depends(get_identity_reader)]

_sms_adapter_instance = FakeSmsSenderAdapter()


def get_sms_sender() -> SmsSenderPort:
    """Provide SMS sender port adapter."""
    return _sms_adapter_instance


SmsSenderDep = Annotated[SmsSenderPort, Depends(get_sms_sender)]
