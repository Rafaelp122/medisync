"""Port for dispatching SMS verification messages."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class SmsSenderPort(Protocol):
    """Port for sending SMS text messages and OTP codes."""

    async def enviar_otp(self, telefone: str, codigo: str) -> None:
        """Send a 6-digit OTP code to the destination phone number."""
        ...


__all__ = ["SmsSenderPort"]
