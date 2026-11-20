"""Optional lookup port for resolving active patient attendance on authentication."""

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class ActiveAttendanceLookupPort(Protocol):
    """Protocol for resolving a patient's active attendance ID."""

    async def buscar_atendimento_ativo_paciente(
        self,
        paciente_id: UUID,
    ) -> UUID | None:
        """Return active attendance UUID for the patient if one is in progress."""
        ...
