"""Public read port for identity lookups across modules without model coupling."""

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
