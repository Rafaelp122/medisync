"""Port for directory lookup of org/physician/patient verification data."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class DadosVerificacaoDirectory:
    """Immutable directory snapshot for public document verification."""

    organizacao_nome: str
    medico_nome: str
    medico_crm: str
    medico_crm_uf: str
    paciente_nome: str
    paciente_cpf: str


@runtime_checkable
class DocumentDirectoryPort(Protocol):
    """Abstract directory for org/physician/patient verification data."""

    async def obter_dados_verificacao(
        self,
        organizacao_id: int,
        medico_id: UUID,
        atendimento_id: UUID,
    ) -> DadosVerificacaoDirectory:
        """Fetch verification snapshot or raise DocumentoIntegridadeError if absent."""
        ...
