"""Logging notification adapter for local testing and open-source deploys."""

import logging
from datetime import UTC, datetime

from src.modules.queue.application.ports.notification_port import NotificationPort

logger: logging.Logger = logging.getLogger("medisync.queue.notifications")


class LoggingNotificationAdapter(NotificationPort):
    """Console/logger notification adapter for local testing and open-source deploys.

    Operates without requiring third-party API credentials (e.g. Twilio, Meta, Z-API).
    Maintains an in-memory buffer of dispatched WhatsApp messages for test inspections.
    """

    def __init__(self) -> None:
        self.sent_whatsapp: list[dict[str, object]] = []

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
        """Clear recorded in-memory WhatsApp messages."""
        self.sent_whatsapp.clear()
