"""Port interface for dispatching SMS verification messages and OTPs."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class SmsSenderPort(Protocol):
    """Abstract port for sending SMS text messages and OTP verification codes."""

    async def enviar_otp(self, telefone: str, codigo: str) -> None:
        """Send a 6-digit OTP code to the specified destination phone number."""
        ...
