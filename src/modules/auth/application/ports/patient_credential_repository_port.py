"""Port interface for persisting and querying patient password credentials."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from src.modules.auth.domain.models.usuario_credencial import UsuarioCredencial


@runtime_checkable
class PatientCredentialRepositoryPort(Protocol):
    """Repository protocol for patient UsuarioCredencial entities."""

    async def buscar_por_identificador(
        self,
        organizacao_id: int,
        identificador: str,
        papel: str,
    ) -> UsuarioCredencial | None:
        """Find a credential by organization, canonical identifier, and role."""
        ...

    async def buscar_por_usuario_id(
        self,
        organizacao_id: int,
        usuario_id: UUID,
        papel: str,
    ) -> UsuarioCredencial | None:
        """Find a credential by organization, user ID, and role."""
        ...

    async def existe_identificador(
        self,
        organizacao_id: int,
        identificador: str,
    ) -> bool:
        """Check whether an identifier is already registered within the organization."""
        ...

    async def criar_credencial(
        self,
        credencial: UsuarioCredencial,
    ) -> UsuarioCredencial:
        """Persist a new UsuarioCredencial without committing the transaction."""
        ...


__all__ = ["PatientCredentialRepositoryPort"]
