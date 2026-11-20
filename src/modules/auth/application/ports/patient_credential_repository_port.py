"""Port interface for persisting and querying patient password credentials."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from src.modules.auth.domain.models.usuario_credencial import UsuarioCredencial


@runtime_checkable
class PatientCredentialRepositoryPort(Protocol):
    """Repository protocol for patient UsuarioCredencial entities."""

    async def buscar_por_identificador(
        self,
        identificador: str,
        papel: str,
    ) -> UsuarioCredencial | None:
        """Find a credential by canonical identifier and role."""
        ...

    async def buscar_por_usuario_id(
        self,
        usuario_id: UUID,
        papel: str,
    ) -> UsuarioCredencial | None:
        """Find a credential by user ID and role."""
        ...

    async def existe_identificador(
        self,
        identificador: str,
    ) -> bool:
        """Check whether an identifier is already registered in the platform."""
        ...

    async def criar_credencial(
        self,
        credencial: UsuarioCredencial,
    ) -> UsuarioCredencial:
        """Persist a new UsuarioCredencial without committing the transaction."""
        ...


__all__ = ["PatientCredentialRepositoryPort"]
