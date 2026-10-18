"""Logging notification adapter for local testing and open-source deploys."""

import logging
from datetime import UTC, datetime
from typing import Any

from src.modules.queue.application.ports.notification_port import NotificationPort

logger: logging.Logger = logging.getLogger("medisync.queue.notifications")


class LoggingNotificationAdapter(NotificationPort):
    """Console/logger notification adapter for local testing and open-source deploys.

    Operates without requiring third-party API credentials (e.g. Twilio, Meta, Z-API).
    Maintains an in-memory buffer of dispatched messages for test inspections.
    """

    def __init__(self) -> None:
        self.sent_sms: list[dict[str, Any]] = []
        self.sent_whatsapp: list[dict[str, Any]] = []

    async def send_sms(self, to: str, message: str) -> bool:
        """Log SMS dispatch and record in memory buffer."""
        logger.info("Notification [SMS] sent to %s: %s", to, message)
        self.sent_sms.append(
            {
                "to": to,
                "message": message,
                "sent_at": datetime.now(UTC),
            }
        )
        return True

    async def send_whatsapp(
        self,
        to: str,
        template: str,
        params: dict[str, str] | None = None,
    ) -> bool:
        """Log WhatsApp dispatch and record in memory buffer."""
        effective_params = params or {}
        logger.info(
            "Notification [WhatsApp] sent to %s [template=%s, params=%s]",
            to,
            template,
            effective_params,
        )
        self.sent_whatsapp.append(
            {
                "to": to,
                "template": template,
                "params": effective_params,
                "sent_at": datetime.now(UTC),
            }
        )
        return True

    def clear(self) -> None:
        """Clear recorded in-memory messages."""
        self.sent_sms.clear()
        self.sent_whatsapp.clear()
