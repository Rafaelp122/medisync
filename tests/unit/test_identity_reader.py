"""Unit tests for SqlIdentityReader (Single Platform / ADR-013)."""

from datetime import date
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import pytest
from src.core.errors import NotFoundError
from src.modules.identity.domain.models import (
    ConfiguracaoUnidade,
    Paciente,
    Profissional,
)
from src.modules.identity.infrastructure.identity_reader_sql import SqlIdentityReader

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class _StubScalarList:
    def __init__(self, value: Any) -> None:
        self._value = value

    def first(self) -> Any:
        return self._value

    def all(self) -> list[Any]:
        if isinstance(self._value, list):
            return list(cast("list[Any]", self._value))
        return [self._value] if self._value is not None else []


class _StubResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalars(self) -> _StubScalarList:
        return _StubScalarList(self._value)


class _StubAsyncSession:
    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)

    async def execute(self, *args: Any, **kwargs: Any) -> _StubResult:
        val = self._results.pop(0) if self._results else None
        return _StubResult(val)


@pytest.mark.asyncio
async def test_identity_reader_sucesso_com_configuracao_unidade() -> None:
    med_id = uuid4()
    pac_id = uuid4()

    unidade = ConfiguracaoUnidade(
        cnpj="12345678000199",
        razao_social="Clinica Central Ltda",
        nome_fantasia="Clinica Central",
        modo_publico_sus=True,
        cnes="2000001",
    )
    prof = Profissional(
        id=med_id,
        cpf="12345678901",
        nome_completo="Dra. Maria Clara",
        email="maria@medisync.com",
        papel="MEDICO",
        crm="12345",
        crm_uf="SP",
    )
    pac = Paciente(
        id=pac_id,
        cpf="111.222.333-44",
        data_nascimento=date(1990, 5, 15),
        telefone="11987654321",
        nome_completo="Carlos Silva",
        logradouro="Rua das Flores",
        numero="123",
        bairro="Centro",
        cidade="Sao Paulo",
        estado="SP",
    )

    session = _StubAsyncSession([unidade, prof, pac])
    reader = SqlIdentityReader(cast("AsyncSession", session))
    dto = await reader.obter_dados_diretorio(med_id, pac_id)

    assert not hasattr(dto, "organizacao_id")
    assert dto.organizacao_nome == "Clinica Central"
    assert dto.organizacao_cnpj == "12345678000199"
    assert dto.cnes == "2000001"
    assert dto.medico_nome == "Dra. Maria Clara"
    assert dto.medico_crm == "12345"
    assert dto.medico_crm_uf == "SP"
    assert dto.paciente_nome == "Carlos Silva"
    assert dto.paciente_cpf == "11122233344"
    assert "Rua das Flores, 123" in (dto.paciente_endereco or "")


@pytest.mark.asyncio
async def test_identity_reader_fallback_sem_configuracao_unidade() -> None:
    med_id = uuid4()
    pac_id = uuid4()

    prof = Profissional(
        id=med_id,
        cpf="12345678901",
        nome_completo="Dr. Joao",
        email="joao@medisync.com",
        papel="MEDICO",
        crm="99999",
        crm_uf="RJ",
    )
    pac = Paciente(
        id=pac_id,
        cpf="11122233344",
        data_nascimento=date(1985, 1, 10),
        telefone="21987654321",
        nome_completo="Ana Souza",
    )

    session = _StubAsyncSession([None, prof, pac])
    reader = SqlIdentityReader(cast("AsyncSession", session))
    dto = await reader.obter_dados_diretorio(med_id, pac_id)

    assert dto.organizacao_nome == "MediSync Pronto-Atendimento Virtual"
    assert dto.organizacao_cnpj is None
    assert dto.cnes is None


@pytest.mark.asyncio
async def test_identity_reader_medico_nao_encontrado_raises() -> None:
    unidade = ConfiguracaoUnidade(
        cnpj="12345678000199",
        razao_social="Unidade Teste",
        nome_fantasia="Unidade Teste",
    )
    session = _StubAsyncSession([unidade, None])
    reader = SqlIdentityReader(cast("AsyncSession", session))

    with pytest.raises(NotFoundError, match="Profissional médico"):
        await reader.obter_dados_diretorio(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_identity_reader_obter_modo_sus() -> None:
    reader_sus = SqlIdentityReader(cast("AsyncSession", _StubAsyncSession([True])))
    assert await reader_sus.obter_modo_sus() is True

    reader_empty = SqlIdentityReader(cast("AsyncSession", _StubAsyncSession([None])))
    assert await reader_empty.obter_modo_sus() is False


@pytest.mark.asyncio
async def test_identity_reader_buscar_paciente_por_telefone_encontrado() -> None:
    pac_id = uuid4()
    pac = Paciente(
        id=pac_id,
        cpf="11144477735",
        data_nascimento=date(1992, 3, 20),
        telefone="11987654321",
        nome_completo="Carlos Teste",
    )
    session = _StubAsyncSession([pac])
    reader = SqlIdentityReader(cast("AsyncSession", session))
    dto = await reader.buscar_paciente_por_telefone(
        telefone="11987654321",
        cpf="11144477735",
    )

    assert dto is not None
    assert not hasattr(dto, "organizacao_id")
    assert dto.id == pac_id
    assert dto.telefone == "11987654321"
    assert dto.cpf == "11144477735"
    assert dto.nome_completo == "Carlos Teste"


@pytest.mark.asyncio
async def test_identity_reader_buscar_paciente_por_telefone_nao_encontrado() -> None:
    session = _StubAsyncSession([None])
    reader = SqlIdentityReader(cast("AsyncSession", session))
    dto = await reader.buscar_paciente_por_telefone(telefone="11999999999")

    assert dto is None
