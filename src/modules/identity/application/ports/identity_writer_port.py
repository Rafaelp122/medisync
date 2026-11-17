"""Public write port for registering patient records across module boundaries."""

from datetime import date
from typing import Protocol, runtime_checkable

from src.modules.identity.application.ports.identity_reader_port import (
    PacienteAuthLookupDTO,
)


@runtime_checkable
class IdentityWriterPort(Protocol):
    """Protocol for registering new patient records without committing."""

    async def criar_paciente(
        self,
        *,
        organizacao_id: int,
        cpf: str,
        nome_completo: str,
        data_nascimento: date,
        telefone: str,
    ) -> PacienteAuthLookupDTO:
        """Persist a new patient record within the tenant without committing."""
        ...


__all__ = ["IdentityWriterPort"]
