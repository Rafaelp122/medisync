"""Billing composition root: eligibility service and adapter providers."""

from src.modules.billing.application.ports.eligibility_notifier import (
    ElegibilidadeNotifierPort,
    LoggingElegibilidadeNotifier,
)
from src.modules.billing.application.ports.eligibility_provider import (
    EligibilityProviderPort,
)
from src.modules.billing.application.services.eligibility_service import (
    ElegibilidadeService,
)
from src.modules.billing.infrastructure.adapters.private_gateway_adapter import (
    PrivateInsuranceGatewayAdapter,
)
from src.modules.billing.infrastructure.adapters.sus_adapter import (
    SusEligibilityAdapter,
)


def get_eligibility_provider(is_sus: bool) -> EligibilityProviderPort:
    """Resolve eligibility provider based on clinic operational mode."""
    if is_sus:
        return SusEligibilityAdapter()
    return PrivateInsuranceGatewayAdapter()


def build_elegibilidade_service(
    is_sus: bool,
    provider: EligibilityProviderPort | None = None,
    notifier: ElegibilidadeNotifierPort | None = None,
) -> ElegibilidadeService:
    """Build ElegibilidadeService outside request scope (worker/task tooling)."""
    resolved_provider = provider or get_eligibility_provider(is_sus=is_sus)
    resolved_notifier = notifier or LoggingElegibilidadeNotifier()
    return ElegibilidadeService(
        provider=resolved_provider,
        notifier=resolved_notifier,
    )
