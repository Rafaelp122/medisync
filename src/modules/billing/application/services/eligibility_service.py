"""Application service orchestrating health insurance and SUS eligibility checks."""

import logging

from src.modules.billing.application.dtos import (
    RequisicaoElegibilidade,
    ResultadoElegibilidade,
)
from src.modules.billing.application.ports import (
    ElegibilidadeFalhaEvent,
    ElegibilidadeNotifierPort,
    EligibilityProviderPort,
    LoggingElegibilidadeNotifier,
)

logger = logging.getLogger("medisync.billing.service")


class ElegibilidadeService:
    """Orchestrates eligibility verification, error handling, and notifications."""

    def __init__(
        self,
        provider: EligibilityProviderPort,
        notifier: ElegibilidadeNotifierPort | None = None,
    ) -> None:
        self._provider = provider
        self._notifier = notifier or LoggingElegibilidadeNotifier()

    async def avaliar_elegibilidade(
        self, requisicao: RequisicaoElegibilidade
    ) -> ResultadoElegibilidade:
        """Verifies eligibility with provider and dispatches alerts on failures."""
        resultado = await self._provider.verificar_elegibilidade(requisicao)

        if not resultado.aprovado:
            motivo_falha = resultado.motivo or "Elegibilidade não confirmada."
            evento = ElegibilidadeFalhaEvent(
                atendimento_id=requisicao.atendimento_id,
                organizacao_id=requisicao.organizacao_id,
                paciente_id=requisicao.paciente_id,
                motivo=motivo_falha,
                status=resultado.status,
            )
            await self._notifier.notificar_falha(evento)

        return resultado
