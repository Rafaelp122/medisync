"""Domain models for queue module."""

from src.modules.queue.domain.models.atendimento import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)

__all__ = [
    "Atendimento",
    "PrioridadeClinica",
    "StatusAtendimento",
]
