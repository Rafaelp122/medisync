"""Data Transfer Objects for identity and onboarding application layer."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.errors import ValidationError
from src.modules.identity.domain.validators import validate_sexo_biologico


class Fase1InputDTO(BaseModel):
    """Input parameters for Phase 1 clinical intake."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    nome_completo: str
    data_nascimento: date
    telefone: str
    queixa_principal: str
    tcle_hash: str
    nome_social: str | None = None
    cpf: str | None = None
    cns: str | None = None


class Fase1OutputDTO(BaseModel):
    """Output results for Phase 1 clinical intake."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    paciente_id: UUID
    token: str
    status: str = "TRIADO_AGUARDANDO_ELEGIBILIDADE"
    mensagem: str
    is_novo_paciente: bool


class Fase2InputDTO(BaseModel):
    """Input parameters for Phase 2 CFM regulatory enrichment."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    paciente_id: UUID
    nome_mae: str
    sexo_biologico: Literal["M", "F"]
    cep: str
    logradouro: str
    numero: str
    bairro: str
    cidade: str
    estado: str
    nome_social: str | None = None
    alergias: list[str] = Field(default_factory=list)
    token: str | None = None

    @field_validator("sexo_biologico", mode="before")
    @classmethod
    def _normalizar_sexo(cls, valor: object) -> str:
        if not isinstance(valor, str):
            raise ValueError(f"Sexo biológico deve ser string; recebido: '{valor}'.")
        try:
            return validate_sexo_biologico(valor)
        except ValidationError as exc:
            raise ValueError(exc.detail) from exc


class Fase2OutputDTO(BaseModel):
    """Enriched patient output adhering to CFM 1.821/2007."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    paciente_id: UUID
    nome_completo: str | None
    nome_social: str | None = None
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


class CriarDependenteDTO(BaseModel):
    """Input parameters for linking or creating a dependent."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    grau_parentesco: str
    dependente_id: UUID | None = None
    nome_completo: str | None = None
    data_nascimento: date | None = None
    cpf: str | None = None
    cns: str | None = None
    telefone: str | None = None


class DependenteOutputDTO(BaseModel):
    """Summary of created dependent relationship."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    organizacao_id: int
    titular_id: UUID
    dependente_id: UUID
    grau_parentesco: str
    vinculado_em: datetime


class DependenteDetalheDTO(BaseModel):
    """Detailed dependent projection including demographics."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    titular_id: UUID
    dependente_id: UUID
    grau_parentesco: str
    nome_completo: str | None
    data_nascimento: date
    cpf: str | None
    cns: str | None
    vinculado_em: datetime
