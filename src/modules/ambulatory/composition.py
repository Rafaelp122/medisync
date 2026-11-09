"""Ambulatory composition root: providers for eligibility and
production services (ADR-012).
"""

from typing import Annotated

from fastapi import Depends

from src.core.audit import SqlAuditTrailAdapter
from src.core.database import DbSessionDep
from src.modules.ambulatory.application.ports.eligibility_notifier import (
    ElegibilidadeNotifierPort,
)
from src.modules.ambulatory.application.ports.eligibility_provider import (
    EligibilityProviderPort,
)
from src.modules.ambulatory.application.services.eligibility_service import (
    ElegibilidadeService,
)
from src.modules.ambulatory.application.services.producao_service import (
    ProducaoAmbulatorialService,
)
from src.modules.ambulatory.infrastructure.adapters.logging_eligibility_notifier import (  # noqa: E501
    LoggingElegibilidadeNotifier,
)
from src.modules.ambulatory.infrastructure.adapters.sus_adapter import (
    SusEligibilityAdapter,
)


def get_eligibility_provider() -> EligibilityProviderPort:
    """Resolve eligibility provider for public SUS instances."""
    return SusEligibilityAdapter()


def build_elegibilidade_service(
    provider: EligibilityProviderPort | None = None,
    notifier: ElegibilidadeNotifierPort | None = None,
) -> ElegibilidadeService:
    """Build ElegibilidadeService outside request scope (worker/task tooling)."""
    resolved_provider = provider or get_eligibility_provider()
    resolved_notifier = notifier or LoggingElegibilidadeNotifier()
    return ElegibilidadeService(
        provider=resolved_provider,
        notifier=resolved_notifier,
    )


def get_producao_ambulatorial_service(
    session: DbSessionDep,
) -> ProducaoAmbulatorialService:
    """Resolve ProducaoAmbulatorialService para rotas e injeção de dependência."""
    return ProducaoAmbulatorialService(
        session=session,
        audit_trail=SqlAuditTrailAdapter(session),
    )


ProducaoServiceDep = Annotated[
    ProducaoAmbulatorialService, Depends(get_producao_ambulatorial_service)
]
