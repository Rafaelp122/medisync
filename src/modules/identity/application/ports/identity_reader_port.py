"""Public read port for identity lookups across modules without model coupling."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class IdentityDirectoryDTO:
    """Consolidated identity directory data for clinical documents and verification."""

    organizacao_id: int
    organizacao_nome: str
    organizacao_cnpj: str | None
    medico_id: UUID
    medico_nome: str
    medico_crm: str | None
    medico_crm_uf: str | None
    paciente_id: UUID
    paciente_nome: str
    paciente_cpf: str | None
    paciente_data_nascimento: date | None
    paciente_endereco: str | None
    paciente_nome_social: str | None = None
    cnes: str | None = None


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

    @property
    def nome_mae(self) -> str | None: ...


@dataclass(frozen=True)
class PacienteAuthLookupData:
    """Concrete immutable representation of patient lookup data."""

    id: UUID
    organizacao_id: int
    telefone: str
    cpf: str | None
    nome_completo: str
    nome_mae: str | None = None


class PacientePasskeyDTO(Protocol):
    """Structural protocol for patient WebAuthn passkey metadata."""

    @property
    def id(self) -> UUID: ...

    @property
    def organizacao_id(self) -> int: ...

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
    organizacao_id: int
    paciente_id: UUID
    credential_id: str
    public_key: str
    sign_count: int = 0
    device_name: str | None = None


@runtime_checkable
class IdentityReaderPort(Protocol):
    """Protocol for reading identity entities using chainable ORM queries."""

    async def obter_dados_diretorio(
        self,
        organizacao_id: int,
        medico_id: UUID,
        paciente_id: UUID,
    ) -> IdentityDirectoryDTO:
        """Fetch verified organization, doctor and patient details."""
        ...

    async def obter_modo_sus(self, organizacao_id: int) -> bool:
        """Check whether the organization operates in public SUS mode."""
        ...

    async def listar_organizacoes_ativas(self) -> list[int]:
        """List primary keys of all active organizations."""
        ...

    async def buscar_paciente_por_telefone(
        self,
        organizacao_id: int,
        telefone: str,
        cpf: str | None = None,
    ) -> PacienteAuthLookupDTO | None:
        """Look up patient authentication record by organization and phone."""
        ...

    async def buscar_paciente_cadsus(
        self,
        organizacao_id: int,
        cpf: str | None = None,
        data_nascimento: date | None = None,
        cns: str | None = None,
        nome_mae: str | None = None,
    ) -> PacienteAuthLookupDTO | None:
        """Look up patient record via CADSUS/Gov.br credentials (CPF, CNS, nome_mae)."""
        ...

    async def buscar_paciente_por_id(
        self,
        organizacao_id: int,
        paciente_id: UUID,
    ) -> PacienteAuthLookupDTO | None:
        """Look up patient authentication record by organization and patient ID."""
        ...

    async def registrar_passkey_paciente(
        self,
        organizacao_id: int,
        paciente_id: UUID,
        credential_id: str,
        public_key: str,
        sign_count: int = 0,
        device_name: str | None = None,
    ) -> PacientePasskeyDTO:
        """Persist or update a FIDO2/WebAuthn passkey bound to a patient record."""
        ...

    async def buscar_passkey_por_credencial(
        self,
        organizacao_id: int,
        credential_id: str,
    ) -> PacientePasskeyDTO | None:
        """Look up a registered WebAuthn passkey by tenant and credential ID."""
        ...

    async def listar_passkeys_paciente(
        self,
        organizacao_id: int,
        paciente_id: UUID,
    ) -> Sequence[PacientePasskeyDTO]:
        """List all registered WebAuthn passkeys for a patient within a tenant."""
        ...
