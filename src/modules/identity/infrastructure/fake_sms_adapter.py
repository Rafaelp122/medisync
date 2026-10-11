"""Fake in-memory SMS sender adapter for testing, CI, and local development."""

import logging
from datetime import UTC, datetime
from typing import Any

from src.modules.identity.application.ports.sms_sender_port import SmsSenderPort

logger = logging.getLogger("medisync.identity.sms")


class FakeSmsSenderAdapter(SmsSenderPort):
    """In-memory and logging SMS sender adapter.

    Operates without third-party telecom credentials (e.g. Twilio, Z-API).
    Logs OTP transmissions and retains sent messages in an in-memory buffer
    for test inspection.
    """

    def __init__(self) -> None:
        self.sent_otps: list[dict[str, Any]] = []

    async def enviar_otp(self, telefone: str, codigo: str) -> None:
        """Log structured OTP dispatch and record in in-memory test buffer."""
        logger.info(
            "Notification [SMS OTP] sent to %s: %s",
            telefone,
            codigo,
        )
        self.sent_otps.append(
            {
                "telefone": telefone,
                "codigo": codigo,
                "sent_at": datetime.now(UTC),
            }
        )

    def clear(self) -> None:
        """Clear recorded in-memory messages."""
        self.sent_otps.clear()
