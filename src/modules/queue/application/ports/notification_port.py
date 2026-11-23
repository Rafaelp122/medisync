"""Queue notification port abstraction (PEP 544 Protocol)."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class NotificationPort(Protocol):
    """Abstract port for dispatching WhatsApp notifications."""

    async def send_whatsapp(
        self,
        to: str,
        template: str,
        params: dict[str, str] | None = None,
    ) -> bool:
        """Send a WhatsApp notification based on template and variable params."""
        ...


__all__ = ["NotificationPort"]
