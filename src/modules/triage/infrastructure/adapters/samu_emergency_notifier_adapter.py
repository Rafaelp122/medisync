"""Concrete emergency notifier adapter for SAMU 192 redirection (RN04, NC-MED-01)."""

import logging
from uuid import UUID

import httpx

from src.modules.triage.application.ports.emergency_notifier import (
    EmergencyAlertDTO,
    EmergencyNotifierPort,
)

logger = logging.getLogger("medisync.triage.samu")


class SamuEmergencyNotifierAdapter(EmergencyNotifierPort):
    """Dispatches emergency alerts for level 1 patients via logs and HTTP webhook."""

    def __init__(
        self,
        webhook_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._http_client = http_client

    async def notificar_emergencia_samu(self, alert: EmergencyAlertDTO) -> None:
        """Dispatches an emergency alert notification for SAMU 192 redirection."""
        logger.critical(
            "CRITICAL EMERGENCY ALERT (SAMU 192) DISPATCHED: "
            "atendimento=%s queixa='%s' sintomas=%s instrucao='%s'",
            alert.atendimento_id,
            alert.queixa_principal,
            alert.sintomas_alerta,
            alert.instrucao_redirecionamento,
            extra={
                "event": "EMERGENCIA_SAMU_192_DISPARADA",
                "atendimento_id": str(alert.atendimento_id),
                "queixa_principal": alert.queixa_principal,
                "sintomas_alerta": alert.sintomas_alerta,
                "disparado_em": alert.disparado_em.isoformat(),
            },
        )

        if not self._webhook_url:
            return

        payload: dict[str, object] = {
            "event": "EMERGENCIA_SAMU_192",
            "atendimento_id": str(alert.atendimento_id),
            "queixa_principal": alert.queixa_principal,
            "sintomas_alerta": alert.sintomas_alerta,
            "instrucao_redirecionamento": alert.instrucao_redirecionamento,
            "disparado_em": alert.disparado_em.isoformat(),
        }
        await self._enviar_webhook(self._webhook_url, payload, alert.atendimento_id)

    async def _enviar_webhook(
        self,
        url: str,
        payload: dict[str, object],
        atendimento_id: UUID,
    ) -> None:
        try:
            if self._http_client is not None:
                response = await self._http_client.post(url, json=payload)
                response.raise_for_status()
                return
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(
                "Failed to dispatch SAMU webhook for attendance %s: %s",
                atendimento_id,
                exc,
                exc_info=True,
            )
