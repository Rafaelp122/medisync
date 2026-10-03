"""Private health insurance gateway adapter with strict 15s timeout (RF-02)."""

import logging
from typing import Any

import httpx
from src.modules.billing.application.dtos import (
    RequisicaoElegibilidade,
    ResultadoElegibilidade,
)
from src.modules.billing.domain.enums import StatusElegibilidade

logger = logging.getLogger("medisync.billing.gateway")

DEFAULT_GATEWAY_TIMEOUT_SECONDS: float = 15.0


class PrivateInsuranceGatewayAdapter:
    """Connects to external health insurance operator gateways with 15s timeout."""

    def __init__(
        self,
        base_url: str = "https://api.operadora.com.br/v1/elegibilidade",
        timeout_segundos: float = DEFAULT_GATEWAY_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout_segundos
        self._client = client

    async def verificar_elegibilidade(
        self, requisicao: RequisicaoElegibilidade
    ) -> ResultadoElegibilidade:
        """Queries operator gateway with 15s timeout, returning result."""
        payload: dict[str, Any] = {
            "organizacao_id": requisicao.organizacao_id,
            "atendimento_id": str(requisicao.atendimento_id),
            "paciente_id": str(requisicao.paciente_id),
            "cpf": requisicao.cpf,
            "cns": requisicao.cns,
            "operadora_id": requisicao.operadora_id,
            "numero_carteirinha": requisicao.numero_carteirinha,
        }

        try:
            if self._client is not None:
                response = await self._client.post(
                    self._base_url,
                    json=payload,
                    timeout=self._timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        self._base_url,
                        json=payload,
                    )

            if response.status_code == 200:
                data: dict[str, Any] = response.json()
                aprovado = bool(data.get("aprovado", False))
                if aprovado:
                    return ResultadoElegibilidade(
                        aprovado=True,
                        status=StatusElegibilidade.APROVADO,
                        codigo_autorizacao=data.get("codigo_autorizacao", "AUTH-OK"),
                    )
                return ResultadoElegibilidade(
                    aprovado=False,
                    status=StatusElegibilidade.REJEITADO,
                    motivo=data.get(
                        "motivo", "Autorização recusada pela operadora de saúde."
                    ),
                )

            logger.warning(
                "Gateway HTTP error status=%d body=%s",
                response.status_code,
                response.text,
            )
            return ResultadoElegibilidade(
                aprovado=False,
                status=StatusElegibilidade.REJEITADO,
                motivo=f"Operadora retornou status HTTP {response.status_code}.",
            )

        except httpx.TimeoutException:
            logger.warning(
                "Eligibility check timed out after %.1fs for attendance %s",
                self._timeout,
                requisicao.atendimento_id,
            )
            return ResultadoElegibilidade(
                aprovado=False,
                status=StatusElegibilidade.TIMEOUT,
                motivo=(
                    f"Tempo limite de {int(self._timeout)}s excedido na consulta "
                    "à operadora de saúde."
                ),
            )
        except Exception as exc:
            logger.error(
                "Unexpected failure communicating with insurance gateway: %s",
                str(exc),
                exc_info=exc,
            )
            return ResultadoElegibilidade(
                aprovado=False,
                status=StatusElegibilidade.REJEITADO,
                motivo=f"Erro de comunicação com a operadora: {exc}",
            )
