"""Emergency notifier port and DTO for SAMU 192 escape (RN04)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

INSTRUCAO_SAMU_PADRAO = (
    "LIGUE 192 IMEDIATAMENTE (SAMU) OU DESLOQUE-SE A UM SERVIÇO DE URGÊNCIA FIXO."
)


@dataclass(frozen=True)
class EmergencyAlertDTO:
    """Immutable data transfer object for level 1 emergency alerts."""

    atendimento_id: UUID
    organizacao_id: int
    queixa_principal: str
    sintomas_alerta: list[str]
    instrucao_redirecionamento: str = INSTRUCAO_SAMU_PADRAO
    disparado_em: datetime = field(default_factory=lambda: datetime.now(UTC))


class EmergencyNotifierPort(Protocol):
    """Abstract port for asynchronous dispatch of critical emergency alerts."""

    async def notificar_emergencia_samu(self, alert: EmergencyAlertDTO) -> None:
        """Dispatches an emergency alert notification for SAMU 192 redirection."""
        ...
