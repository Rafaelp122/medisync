"""Public write port for registering patient records from the auth module."""

from datetime import date
from typing import Protocol, runtime_checkable

from src.modules.auth.application.ports.identity_reader_port import (
    PacienteAuthLookupDTO,
)


@runtime_checkable
class IdentityWriterPort(Protocol):
    """Protocol for registering new patient records without cross-module coupling."""

    async def criar_paciente(
        self,
        *,
        organizacao_id: int,
        cpf: str,
        nome_completo: str,
        data_nascimento: date,
        telefone: str,
    ) -> PacienteAuthLookupDTO:
        """Create a new patient record in the identity module without committing."""
        ...


__all__ = ["IdentityWriterPort"]
