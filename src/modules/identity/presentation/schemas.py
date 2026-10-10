"""Pydantic v2 schemas for progressive onboarding and patient management."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from src.modules.identity.application.dtos import (
    CriarDependenteDTO,
    DependenteDetalheDTO,
    DependenteOutputDTO,
    Fase1InputDTO,
    Fase1OutputDTO,
    Fase2InputDTO,
    Fase2OutputDTO,
)


class Fase1Request(Fase1InputDTO):
    """Payload for Phase 1 clinical intake."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    nome_completo: str = Field(
        min_length=3,
        max_length=255,
        description="Nome completo do paciente",
        examples=["Maria da Silva"],
    )
    data_nascimento: date = Field(
        description="Data de nascimento do paciente",
        examples=["1985-05-15"],
    )
    telefone: str = Field(
        min_length=10,
        max_length=20,
        description="Telefone de contato com DDD",
        examples=["11987654321"],
    )
    queixa_principal: str = Field(
        min_length=3,
        max_length=1000,
        description="Queixa principal relatada pelo paciente",
        examples=["Dor de cabeça intensa e febre há 2 dias"],
    )
    tcle_hash: str = Field(
        min_length=64,
        max_length=64,
        description="Hash SHA-256 do aceite digital do TCLE",
        examples=["e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"],
    )
    cpf: str | None = Field(
        default=None,
        max_length=14,
        description="Cadastro de Pessoas Físicas (CPF)",
        examples=["11144477735"],
    )
    cns: str | None = Field(
        default=None,
        max_length=18,
        description="Cartão Nacional de Saúde (CNS)",
        examples=["700000000000005"],
    )


class Fase1Response(Fase1OutputDTO):
    """Response after Phase 1 intake execution."""

    model_config = ConfigDict(from_attributes=True)


class Fase2Request(Fase2InputDTO):
    """Payload for Phase 2 CFM regulatory enrichment."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    paciente_id: UUID = Field(description="ID do paciente obtido na Fase 1")
    nome_mae: str = Field(
        min_length=3,
        max_length=255,
        description="Nome completo da mãe do paciente (CFM 1.821/2007)",
        examples=["Ana Lúcia da Silva"],
    )
    sexo_biologico: Literal["M", "F"] = Field(
        description="Sexo biológico: 'M' (Masculino) ou 'F' (Feminino)",
        examples=["F"],
    )
    cep: str = Field(
        min_length=8,
        max_length=9,
        description="Código de Endereçamento Postal (CEP)",
        examples=["01310-100"],
    )
    logradouro: str = Field(
        min_length=2,
        max_length=255,
        description="Logradouro / Rua / Avenida",
        examples=["Avenida Paulista"],
    )
    numero: str = Field(
        min_length=1,
        max_length=20,
        description="Número do imóvel",
        examples=["1000"],
    )
    bairro: str = Field(
        min_length=2,
        max_length=100,
        description="Bairro",
        examples=["Bela Vista"],
    )
    cidade: str = Field(
        min_length=2,
        max_length=100,
        description="Cidade / Município",
        examples=["São Paulo"],
    )
    estado: str = Field(
        min_length=2,
        max_length=2,
        description="Unidade Federativa (UF)",
        examples=["SP"],
    )
    alergias: list[str] = Field(
        default_factory=list,
        description="Lista de alergias medicamentosas declaradas",
        examples=[["Dipirona", "Penicilina"]],
    )
    token: str | None = Field(
        default=None,
        description=(
            "Token provisório de acolhimento (intake_token) gerado na Fase 1. "
            "Alternativamente, pode ser enviado via cabeçalho "
            "Authorization: Bearer <token>."
        ),
        examples=["eyJhbGciOi..."],
    )


class Fase2Response(Fase2OutputDTO):
    """Response after Phase 2 CFM regulatory enrichment."""

    model_config = ConfigDict(from_attributes=True)


class CriarDependenteRequest(CriarDependenteDTO):
    """Payload for linking or creating a patient dependent."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    grau_parentesco: str = Field(
        min_length=2,
        max_length=32,
        description="Grau de parentesco (FILHO, FILHA, ENTEADO, TUTELADO, etc.)",
        examples=["FILHO"],
    )
    dependente_id: UUID | None = Field(
        default=None,
        description="ID do paciente dependente caso já possua cadastro",
    )
    nome_completo: str | None = Field(
        default=None,
        min_length=3,
        max_length=255,
        description="Nome do dependente para cadastro de novo paciente",
        examples=["João da Silva"],
    )
    data_nascimento: date | None = Field(
        default=None,
        description="Data de nascimento do dependente",
        examples=["2020-01-10"],
    )
    cpf: str | None = Field(
        default=None,
        max_length=14,
        description="CPF do dependente",
        examples=["52998224725"],
    )
    cns: str | None = Field(
        default=None,
        max_length=18,
        description="CNS do dependente",
        examples=["700000000000005"],
    )
    telefone: str | None = Field(
        default=None,
        max_length=20,
        description="Telefone de contato do dependente (opcional, herda do titular)",
    )


class DependenteResponse(DependenteOutputDTO):
    """Summary of created dependent relationship."""

    model_config = ConfigDict(from_attributes=True)


class DependenteDetalheResponse(DependenteDetalheDTO):
    """Full detail of a dependent including clinical demographics."""

    model_config = ConfigDict(from_attributes=True)
