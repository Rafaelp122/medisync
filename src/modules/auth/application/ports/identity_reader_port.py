"""Public read port for patient identity lookups in auth module."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


class PacienteAuthLookupDTO(Protocol):
    """Structural protocol for patient authentication lookup data."""

    @property
    def id(self) -> UUID: ...

    @property
    def organizacao_id(self) -> int: ...

    @property
    def telefone(self) -> str: ...

    @property
    def cpf(self) -> str | None: ...

    @property
    def nome_completo(self) -> str: ...


@dataclass(frozen=True)
class PacienteAuthLookupData:
    """Concrete immutable representation of patient lookup data."""

    id: UUID
    organizacao_id: int
    telefone: str
    cpf: str | None
    nome_completo: str


@runtime_checkable
class IdentityReaderPort(Protocol):
    """Protocol for reading patient identity records for authentication."""

    async def buscar_paciente_por_telefone(
        self,
        organizacao_id: int,
        telefone: str,
        cpf: str | None = None,
    ) -> PacienteAuthLookupDTO | None:
        """Look up patient record by organization and telephone number."""
        ...


__all__ = ["IdentityReaderPort", "PacienteAuthLookupDTO", "PacienteAuthLookupData"]
