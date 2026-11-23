"""Cross-module port for synchronizing active medical shift presence."""

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class DoctorPresencePort(Protocol):
    """Port for updating active doctor presence on auth login and logout."""

    async def registrar_medico_ativo(self, medico_id: UUID) -> None:
        """Register authenticated doctor in active shift presence store."""
        ...

    async def desregistrar_medico_ativo(self, medico_id: UUID) -> None:
        """Unregister doctor from active shift presence store on logout."""
        ...


__all__ = ["DoctorPresencePort"]
