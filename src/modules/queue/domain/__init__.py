"""Queue domain layer."""

from src.modules.queue.domain.exceptions import TransicaoEstadoInvalidaError
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)

__all__ = [
    "Atendimento",
    "PrioridadeClinica",
    "StatusAtendimento",
    "TransicaoEstadoInvalidaError",
]
