"""Data Transfer Objects and structural input protocols for identity layer (ADR-008)."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol
from uuid import UUID


class Fase1Input(Protocol):
    """Structural contract satisfied directly by Fase1Request."""

    @property
    def nome_completo(self) -> str: ...

    @property
    def data_nascimento(self) -> date: ...

    @property
    def telefone(self) -> str: ...

    @property
    def queixa_principal(self) -> str: ...

    @property
    def tcle_hash(self) -> str: ...

    @property
    def nome_social(self) -> str | None: ...

    @property
    def cpf(self) -> str | None: ...

    @property
    def cns(self) -> str | None: ...


@dataclass(frozen=True)
class Fase1OutputDTO:
    """Immutable output results for Phase 1 clinical intake."""

    paciente_id: UUID
    token: str
    status: str
    mensagem: str
    is_novo_paciente: bool


class Fase2Input(Protocol):
    """Structural contract satisfied directly by Fase2Request."""

    @property
    def paciente_id(self) -> UUID: ...

    @property
    def nome_social(self) -> str | None: ...

    @property
    def nome_mae(self) -> str: ...

    @property
    def sexo_biologico(self) -> Literal["M", "F"]: ...

    @property
    def cep(self) -> str: ...

    @property
    def logradouro(self) -> str: ...

    @property
    def numero(self) -> str: ...

    @property
    def bairro(self) -> str: ...

    @property
    def cidade(self) -> str: ...

    @property
    def estado(self) -> str: ...

    @property
    def alergias(self) -> list[str]: ...

    @property
    def token(self) -> str | None: ...


@dataclass(frozen=True)
class Fase2OutputDTO:
    """Enriched patient output adhering to CFM 1.821/2007."""

    paciente_id: UUID
    nome_completo: str | None
    nome_social: str | None
    nome_mae: str
    sexo_biologico: str
    cep: str
    logradouro: str
    numero: str
    bairro: str
    cidade: str
    estado: str
    alergias: list[str]
    status: str


class CriarDependenteInput(Protocol):
    """Structural contract satisfied directly by CriarDependenteRequest."""

    @property
    def grau_parentesco(self) -> str: ...

    @property
    def dependente_id(self) -> UUID | None: ...

    @property
    def nome_completo(self) -> str | None: ...

    @property
    def data_nascimento(self) -> date | None: ...

    @property
    def cpf(self) -> str | None: ...

    @property
    def cns(self) -> str | None: ...

    @property
    def telefone(self) -> str | None: ...

    @property
    def outorga_tcle(self) -> bool: ...


@dataclass(frozen=True)
class DependenteOutputDTO:
    """Summary of created dependent relationship."""

    id: UUID
    titular_id: UUID
    dependente_id: UUID
    grau_parentesco: str
    vinculado_em: datetime
    outorga_tcle: bool = False


@dataclass(frozen=True)
class DependenteDetalheDTO:
    """Full detail of a dependent including clinical demographics."""

    id: UUID
    titular_id: UUID
    dependente_id: UUID
    grau_parentesco: str
    nome_completo: str | None
    data_nascimento: date
    cpf: str | None
    cns: str | None
    vinculado_em: datetime
    outorga_tcle: bool = False


__all__ = [
    "CriarDependenteInput",
    "DependenteDetalheDTO",
    "DependenteOutputDTO",
    "Fase1Input",
    "Fase1OutputDTO",
    "Fase2Input",
    "Fase2OutputDTO",
]
