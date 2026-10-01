"""Typed model factories for identity entities used across tests."""

from datetime import date
from typing import Any
from uuid import UUID

from src.core.uuid7 import uuid7
from src.modules.identity.domain.models import (
    Dependente,
    Organizacao,
    Paciente,
    Profissional,
)


def make_organizacao(
    *,
    cnpj: str = "12345678000195",
    razao_social: str = "Unidade Básica de Saúde Central",
    nome_fantasia: str = "UBS Central",
    modo_publico_sus: bool = True,
    config_plantao: dict[str, Any] | None = None,
    ativo: bool = True,
    id: int | None = None,
) -> Organizacao:
    return Organizacao(
        cnpj=cnpj,
        razao_social=razao_social,
        nome_fantasia=nome_fantasia,
        modo_publico_sus=modo_publico_sus,
        config_plantao=config_plantao,
        ativo=ativo,
        id=id,
    )


def make_profissional(
    organizacao_id: int = 1,
    *,
    cpf: str = "11122233344",
    nome_completo: str = "Dr. Carlos Plantonista",
    email: str = "carlos@medisync.local",
    senha_hash: str = "hash-default",
    papel: str = "MEDICO",
    crm: str | None = "998877",
    crm_uf: str | None = "SP",
    ativo: bool = True,
    id: UUID | None = None,
) -> Profissional:
    return Profissional(
        organizacao_id=organizacao_id,
        cpf=cpf,
        nome_completo=nome_completo,
        email=email,
        senha_hash=senha_hash,
        papel=papel,
        crm=crm,
        crm_uf=crm_uf,
        ativo=ativo,
        id=id or uuid7(),
    )


def make_paciente(
    organizacao_id: int = 1,
    *,
    cpf: str | None = "55566677788",
    cns: str | None = None,
    data_nascimento: date | None = None,
    nome_completo: str = "Maria dos Santos",
    telefone: str = "11987654321",
    alergias: list[str] | None = None,
    id: UUID | None = None,
) -> Paciente:
    return Paciente(
        organizacao_id=organizacao_id,
        cpf=cpf,
        cns=cns,
        data_nascimento=data_nascimento or date(1985, 3, 15),
        nome_completo=nome_completo,
        telefone=telefone,
        alergias=alergias,
        id=id or uuid7(),
    )


def make_dependente(
    organizacao_id: int = 1,
    titular_id: UUID | None = None,
    dependente_id: UUID | None = None,
    *,
    grau_parentesco: str = "FILHO",
    id: UUID | None = None,
) -> Dependente:
    return Dependente(
        organizacao_id=organizacao_id,
        titular_id=titular_id or uuid7(),
        dependente_id=dependente_id or uuid7(),
        grau_parentesco=grau_parentesco,
        id=id or uuid7(),
    )
