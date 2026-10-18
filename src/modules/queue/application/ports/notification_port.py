"""Queue notification port abstraction (PEP 544 Protocol)."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class NotificationPort(Protocol):
    """Abstract port for dispatching SMS and WhatsApp notifications."""

    async def send_sms(self, to: str, message: str) -> bool:
        """Send an SMS text message to the given destination phone number."""
        ...

    async def send_whatsapp(
        self,
        to: str,
        template: str,
        params: dict[str, str] | None = None,
    ) -> bool:
        """Send a WhatsApp notification based on template and variable params."""
        ...


__all__ = ["NotificationPort"]
