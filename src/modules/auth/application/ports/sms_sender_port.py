"""Port for dispatching SMS verification messages."""

from src.modules.identity.application.ports.sms_sender_port import (  # tach-ignore
    SmsSenderPort,
)

__all__ = ["SmsSenderPort"]
