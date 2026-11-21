"""Public read port for patient identity lookups in auth module."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable
from uuid import UUID


class PacienteAuthLookupDTO(Protocol):
    """Structural protocol for patient authentication lookup data."""

    @property
    def id(self) -> UUID: ...

    @property
    def telefone(self) -> str: ...

    @property
    def cpf(self) -> str | None: ...

    @property
    def nome_completo(self) -> str: ...

    @property
    def nome_mae(self) -> str | None: ...

    @property
    def cns(self) -> str | None: ...

    @property
    def data_nascimento(self) -> date | None: ...


@dataclass(frozen=True)
class PacienteAuthLookupData:
    """Concrete immutable representation of patient lookup data."""

    id: UUID
    telefone: str
    cpf: str | None
    nome_completo: str
    nome_mae: str | None = None
    cns: str | None = None
    data_nascimento: date | None = None


class PacientePasskeyDTO(Protocol):
    """Structural protocol for patient WebAuthn passkey metadata."""

    @property
    def id(self) -> UUID: ...

    @property
    def paciente_id(self) -> UUID: ...

    @property
    def credential_id(self) -> str: ...

    @property
    def public_key(self) -> str: ...

    @property
    def sign_count(self) -> int: ...

    @property
    def device_name(self) -> str | None: ...


@dataclass(frozen=True)
class PacientePasskeyData:
    """Concrete immutable representation of a registered patient passkey."""

    id: UUID
    paciente_id: UUID
    credential_id: str
    public_key: str
    sign_count: int = 0
    device_name: str | None = None


@runtime_checkable
class IdentityReaderPort(Protocol):
    """Read-only protocol for querying patient identity records for authentication."""

    async def buscar_paciente_por_telefone(
        self,
        telefone: str,
        cpf: str | None = None,
    ) -> PacienteAuthLookupDTO | None:
        """Look up patient record by telephone number."""
        ...

    async def buscar_paciente_cadsus(
        self,
        cpf: str | None = None,
        data_nascimento: date | None = None,
        cns: str | None = None,
        nome_mae: str | None = None,
    ) -> PacienteAuthLookupDTO | None:
        """Look up patient record via CADSUS/Gov.br credentials (CPF, CNS, nome_mae)."""
        ...

    async def buscar_paciente_por_id(
        self,
        paciente_id: UUID,
    ) -> PacienteAuthLookupDTO | None:
        """Look up patient authentication record by patient ID."""
        ...

    async def buscar_passkey_por_credencial(
        self,
        credential_id: str,
    ) -> PacientePasskeyDTO | None:
        """Look up a registered WebAuthn passkey by credential ID."""
        ...

    async def listar_passkeys_paciente(
        self,
        paciente_id: UUID,
    ) -> Sequence[PacientePasskeyDTO]:
        """List all registered WebAuthn passkeys for a patient."""
        ...
