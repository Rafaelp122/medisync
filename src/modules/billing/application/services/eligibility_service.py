"""Application service orchestrating health insurance and SUS eligibility checks."""

import logging

from src.core.errors import TenantInvalidoError, ValidationError
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
    """Orquestra avaliação de cobertura de convênio/SUS com notificação assíncrona.

    Regras: RN03 (Elegibilidade concorrente em background), RF-02, RF-05, RT-01.
    Documentação: docs/explanation/domains/billing-domain.md e
    docs/adrs/ADR-003-Elegibilidade-Assincrona-ARQ.md
    """

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
        """Avalia cobertura junto ao provedor e dispara alerta à espera se reprovado.

        Regras: RN03 (Elegibilidade concorrente), RF-02, RF-05.
        Documentação: docs/explanation/domains/billing-domain.md
        """
        if requisicao.organizacao_id <= 0:
            raise TenantInvalidoError(
                f"Identificador da organização '{requisicao.organizacao_id}' deve "
                "ser positivo; esperado valor > 0."
            )

        if requisicao.operadora_id is not None and not requisicao.operadora_id.strip():
            raise ValidationError(
                f"Identificador de operadora '{requisicao.operadora_id}' inválido; "
                "esperado identificador alfanumérico não-vazio."
            )

        if (
            requisicao.numero_carteirinha is not None
            and not requisicao.numero_carteirinha.strip()
        ):
            raise ValidationError(
                f"Número de carteirinha '{requisicao.numero_carteirinha}' inválido "
                f"para a operadora '{requisicao.operadora_id or 'NÃO INFORMADA'}'; "
                "esperado identificador alfanumérico não-vazio."
            )

        resultado = await self._provider.verificar_elegibilidade(requisicao)

        if not resultado.aprovado:
            motivo_falha = resultado.motivo or (
                f"Elegibilidade não confirmada para operadora "
                f"'{requisicao.operadora_id or 'NÃO INFORMADA'}' e carteirinha "
                f"'{requisicao.numero_carteirinha or 'NÃO INFORMADA'}'."
            )
            evento = ElegibilidadeFalhaEvent(
                atendimento_id=requisicao.atendimento_id,
                organizacao_id=requisicao.organizacao_id,
                paciente_id=requisicao.paciente_id,
                motivo=motivo_falha,
                status=resultado.status,
            )
            await self._notifier.notificar_falha(evento)

        return resultado
