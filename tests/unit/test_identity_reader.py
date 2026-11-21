"""Unit tests for SqlIdentityReader (Single Platform / ADR-013)."""

from datetime import date
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest
from src.core.errors import ConflictError, NotFoundError, ValidationError
from src.modules.identity.domain.models import (
    ConfiguracaoUnidade,
    Paciente,
    Profissional,
)
from src.modules.identity.infrastructure.identity_reader_sql import SqlIdentityReader

from tests.doubles import FakeAsyncSession, FakeResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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

    session = FakeAsyncSession(
        results=[FakeResult(unidade), FakeResult(prof), FakeResult(pac)]
    )
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

    session = FakeAsyncSession(
        results=[FakeResult(None), FakeResult(prof), FakeResult(pac)]
    )
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
    session = FakeAsyncSession(results=[FakeResult(unidade), FakeResult(None)])
    reader = SqlIdentityReader(cast("AsyncSession", session))

    with pytest.raises(NotFoundError, match="Profissional médico"):
        await reader.obter_dados_diretorio(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_identity_reader_obter_modo_sus() -> None:
    reader_sus = SqlIdentityReader(
        cast("AsyncSession", FakeAsyncSession(results=[FakeResult(True)]))
    )
    assert await reader_sus.obter_modo_sus() is True

    reader_empty = SqlIdentityReader(
        cast("AsyncSession", FakeAsyncSession(results=[FakeResult(None)]))
    )
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
    session = FakeAsyncSession(results=[FakeResult(pac)])
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
    session = FakeAsyncSession(results=[FakeResult(None)])
    reader = SqlIdentityReader(cast("AsyncSession", session))
    dto = await reader.buscar_paciente_por_telefone(telefone="11999999999")

    assert dto is None


@pytest.mark.asyncio
async def test_identity_reader_cadsus_bloqueia_query_vazia_e_ambigua() -> None:
    """CADSUS lookup must block empty criteria and ambiguous multi-row matches."""
    reader_empty = SqlIdentityReader(cast("AsyncSession", FakeAsyncSession()))
    with pytest.raises(ValidationError, match="ao menos CPF ou CNS"):
        await reader_empty.buscar_paciente_cadsus(
            cpf=None,
            cns=None,
            data_nascimento=date(1990, 1, 1),
        )

    p1 = Paciente(
        cpf="11144477735",
        data_nascimento=date(1990, 1, 1),
        telefone="11987654321",
        nome_completo="Paciente Um",
    )
    p2 = Paciente(
        cpf="52998224725",
        data_nascimento=date(1990, 1, 1),
        telefone="11987654322",
        nome_completo="Paciente Dois",
    )
    reader_ambiguous = SqlIdentityReader(
        cast("AsyncSession", FakeAsyncSession(results=[FakeResult([p1, p2])]))
    )
    with pytest.raises(ConflictError, match="múltiplos registros ambíguos"):
        await reader_ambiguous.buscar_paciente_cadsus(
            cpf="11144477735",
            data_nascimento=date(1990, 1, 1),
        )
