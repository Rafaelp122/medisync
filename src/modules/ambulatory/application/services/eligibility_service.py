"""Application service orchestrating health insurance and SUS eligibility checks."""

import logging

from src.core.errors import TenantInvalidoError
from src.modules.ambulatory.application.dtos import (
    RequisicaoElegibilidade,
    ResultadoElegibilidade,
)
from src.modules.ambulatory.application.ports import (
    ElegibilidadeFalhaEvent,
    ElegibilidadeNotifierPort,
    EligibilityProviderPort,
)

logger = logging.getLogger("medisync.ambulatory.service")


class ElegibilidadeService:
    """Orquestra avaliação de cobertura e qualificação SUS com notificação assíncrona.

    Regras: RN03 (Elegibilidade concorrente em background), RF-02, RF-05, RT-01.
    Decisões: ADR-012.
    Documentação: docs/explanation/domains/ambulatory-domain.md e
    docs/adrs/ADR-012-Transicao-100-SUS-Consorcios-Intermunicipais-e-Autenticacao-Tripartida.md
    """

    def __init__(
        self,
        provider: EligibilityProviderPort,
        notifier: ElegibilidadeNotifierPort | None = None,
    ) -> None:
        self._provider = provider
        self._notifier = notifier

    async def avaliar_elegibilidade(
        self, requisicao: RequisicaoElegibilidade
    ) -> ResultadoElegibilidade:
        """Avalia cobertura junto ao provedor e dispara alerta à espera se reprovado.

        Regras: RN03 (Elegibilidade concorrente), RF-02, RF-05, ADR-012.
        Documentação: docs/explanation/domains/ambulatory-domain.md
        """
        if requisicao.organizacao_id <= 0:
            raise TenantInvalidoError(
                f"Identificador da organização '{requisicao.organizacao_id}' deve "
                "ser positivo; esperado valor > 0."
            )

        resultado = await self._provider.verificar_elegibilidade(requisicao)

        if not resultado.aprovado:
            motivo_falha = resultado.motivo or (
                f"Elegibilidade SUS não confirmada para paciente "
                f"'{requisicao.paciente_id}'."
            )
            evento = ElegibilidadeFalhaEvent(
                atendimento_id=requisicao.atendimento_id,
                organizacao_id=requisicao.organizacao_id,
                paciente_id=requisicao.paciente_id,
                motivo=motivo_falha,
                status=resultado.status,
            )
            if self._notifier is not None:
                await self._notifier.notificar_falha(evento)

        return resultado
