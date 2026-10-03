"""Abstract port for eligibility verification providers (PEP 544)."""

from typing import Protocol

from src.modules.billing.application.dtos import (
    RequisicaoElegibilidade,
    ResultadoElegibilidade,
)


class EligibilityProviderPort(Protocol):
    """Abstract interface defining contracts for SUS and private providers."""

    async def verificar_elegibilidade(
        self, requisicao: RequisicaoElegibilidade
    ) -> ResultadoElegibilidade:
        """Verifies eligibility for an attendance asynchronously."""
        ...
