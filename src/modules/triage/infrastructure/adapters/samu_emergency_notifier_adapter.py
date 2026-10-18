"""Concrete emergency notifier adapter for SAMU 192 redirection (RN04, NC-MED-01)."""

import logging
from typing import Any

import httpx

from src.modules.triage.application.ports.emergency_notifier import (
    EmergencyAlertDTO,
    EmergencyNotifierPort,
)

logger = logging.getLogger("medisync.triage.samu")


class SamuEmergencyNotifierAdapter(EmergencyNotifierPort):
    """Dispatches emergency alerts for level 1 patients via structured logs.

    Retains an audit buffer and ensures that whenever an emergency deterioration
    or level 1 risk is detected, a structured critical alert is emitted.
    """

    def __init__(
        self,
        webhook_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._http_client = http_client
        self.sent_alerts: list[EmergencyAlertDTO] = []

    async def notificar_emergencia_samu(self, alert: EmergencyAlertDTO) -> None:
        """Dispatches an emergency alert notification for SAMU 192 redirection."""
        logger.critical(
            "CRITICAL EMERGENCY ALERT (SAMU 192) DISPATCHED: "
            "org=%d atendimento=%s queixa='%s' sintomas=%s instrucao='%s'",
            alert.organizacao_id,
            alert.atendimento_id,
            alert.queixa_principal,
            alert.sintomas_alerta,
            alert.instrucao_redirecionamento,
            extra={
                "event": "EMERGENCIA_SAMU_192_DISPARADA",
                "organizacao_id": alert.organizacao_id,
                "atendimento_id": str(alert.atendimento_id),
                "queixa_principal": alert.queixa_principal,
                "sintomas_alerta": alert.sintomas_alerta,
                "disparado_em": alert.disparado_em.isoformat(),
            },
        )

        self.sent_alerts.append(alert)

        if not self._webhook_url:
            return

        payload: dict[str, Any] = {
            "event": "EMERGENCIA_SAMU_192",
            "organizacao_id": alert.organizacao_id,
            "atendimento_id": str(alert.atendimento_id),
            "queixa_principal": alert.queixa_principal,
            "sintomas_alerta": alert.sintomas_alerta,
            "instrucao_redirecionamento": alert.instrucao_redirecionamento,
            "disparado_em": alert.disparado_em.isoformat(),
        }
        await self._enviar_webhook(self._webhook_url, payload, alert.atendimento_id)

    async def _enviar_webhook(
        self, url: str, payload: dict[str, Any], atendimento_id: object
    ) -> None:
        try:
            if self._http_client is not None:
                await self._http_client.post(url, json=payload)
                return
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json=payload)
        except Exception as exc:
            logger.error(
                "Failed to dispatch SAMU webhook for attendance %s: %s",
                atendimento_id,
                exc,
            )

    def clear(self) -> None:
        """Clear recorded in-memory alerts (primarily for testing)."""
        self.sent_alerts.clear()
