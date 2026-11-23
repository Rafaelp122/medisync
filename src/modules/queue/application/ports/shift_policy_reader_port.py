"""Port and DTO for reading active shift operational policies without module cycles."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ShiftPolicyDTO:
    """Immutable snapshot of shift backpressure, quota, TMA, and ring tolerance."""

    alpha_backpressure: float = 1.25
    cota_diaria_maxima: int | None = 300
    tma_padrao_segundos: int = 600
    tempo_tolerancia_ring_segundos: int = 45


@runtime_checkable
class ShiftPolicyReaderPort(Protocol):
    """Read-only port providing current platform shift policy parameters."""

    async def obter_politica_atual(self) -> ShiftPolicyDTO:
        """Fetch active shift operational configuration (or sensible defaults)."""
        ...


__all__ = ["ShiftPolicyDTO", "ShiftPolicyReaderPort"]
