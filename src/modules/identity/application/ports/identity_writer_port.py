"""Public write port for registering patient and passkey records across modules."""

from datetime import date
from typing import Protocol, runtime_checkable
from uuid import UUID

from src.modules.identity.application.ports.identity_reader_port import (
    PacienteAuthLookupDTO,
    PacientePasskeyDTO,
)


@runtime_checkable
class IdentityWriterPort(Protocol):
    """CQRS write port for patient and passkey persistence without committing."""

    async def criar_paciente(
        self,
        *,
        cpf: str,
        nome_completo: str,
        data_nascimento: date,
        telefone: str,
    ) -> PacienteAuthLookupDTO:
        """Persist a new patient record in the platform without committing."""
        ...

    async def registrar_passkey_paciente(
        self,
        paciente_id: UUID,
        credential_id: str,
        public_key: str,
        sign_count: int = 0,
        device_name: str | None = None,
    ) -> PacientePasskeyDTO:
        """Persist a FIDO2/WebAuthn passkey bound to a patient without committing."""
        ...

    async def atualizar_sign_count_passkey(
        self,
        credential_id: str,
        novo_sign_count: int,
    ) -> PacientePasskeyDTO:
        """Update monotonic FIDO2 signature counter without committing."""
        ...


__all__ = ["IdentityWriterPort"]
