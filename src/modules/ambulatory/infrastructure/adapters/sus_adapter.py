"""No-op eligibility adapter for public SUS deployments (RT-01, RF-02)."""

from src.modules.billing.application.dtos import (
    RequisicaoElegibilidade,
    ResultadoElegibilidade,
)
from src.modules.billing.domain.enums import StatusElegibilidade


class SusEligibilityAdapter:
    """Instant authorization adapter for public SUS healthcare instances.

    Under modo_publico_sus = True, eligibility validation executes as a no-op
    without external network communication, returning immediate approval.
    """

    async def verificar_elegibilidade(
        self, requisicao: RequisicaoElegibilidade
    ) -> ResultadoElegibilidade:
        """Immediately approves public patient attendance."""
        return ResultadoElegibilidade(
            aprovado=True,
            status=StatusElegibilidade.APROVADO,
            codigo_autorizacao="SUS-ISENTO",
        )
