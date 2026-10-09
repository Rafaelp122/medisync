"""Unit tests for SqlIdentityReader."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from src.core.errors import NotFoundError
from src.modules.identity.infrastructure.identity_reader_sql import SqlIdentityReader


async def test_identity_reader_sucesso() -> None:
    session = AsyncMock()
    org_id = 1
    med_id = uuid4()
    pac_id = uuid4()

    mock_org = MagicMock()
    mock_org.nome_fantasia = "Clinica Central"
    mock_org.razao_social = "Clinica Central Ltda"
    mock_org.cnpj = "12345678000199"

    mock_prof = MagicMock()
    mock_prof.id = med_id
    mock_prof.nome_completo = "Dra. Maria Clara"
    mock_prof.crm = "12345"
    mock_prof.crm_uf = "SP"

    mock_pac = MagicMock()
    mock_pac.id = pac_id
    mock_pac.nome_completo = "Carlos Silva"
    mock_pac.cpf = "111.222.333-44"
    mock_pac.data_nascimento = date(1990, 5, 15)
    mock_pac.logradouro = "Rua das Flores"
    mock_pac.numero = "123"
    mock_pac.bairro = "Centro"
    mock_pac.cidade = "Sao Paulo"
    mock_pac.estado = "SP"

    # session.execute returns mock results
    mock_res_org = MagicMock()
    mock_res_org.scalar_one_or_none.return_value = mock_org
    mock_res_prof = MagicMock()
    mock_res_prof.scalar_one_or_none.return_value = mock_prof
    mock_res_pac = MagicMock()
    mock_res_pac.scalar_one_or_none.return_value = mock_pac

    session.execute.side_effect = [mock_res_org, mock_res_prof, mock_res_pac]

    reader = SqlIdentityReader(session)
    dto = await reader.obter_dados_diretorio(org_id, med_id, pac_id)

    assert dto.organizacao_nome == "Clinica Central"
    assert dto.organizacao_cnpj == "12345678000199"
    assert dto.medico_nome == "Dra. Maria Clara"
    assert dto.medico_crm == "12345"
    assert dto.medico_crm_uf == "SP"
    assert dto.paciente_nome == "Carlos Silva"
    assert dto.paciente_cpf == "111.222.333-44"
    assert "Rua das Flores, 123" in (dto.paciente_endereco or "")


async def test_identity_reader_medico_nao_encontrado_raises() -> None:
    session = AsyncMock()
    mock_org = MagicMock()
    mock_res_org = MagicMock()
    mock_res_org.scalar_one_or_none.return_value = mock_org
    mock_res_prof = MagicMock()
    mock_res_prof.scalar_one_or_none.return_value = None

    session.execute.side_effect = [mock_res_org, mock_res_prof]
    reader = SqlIdentityReader(session)

    with pytest.raises(NotFoundError, match="Profissional médico"):
        await reader.obter_dados_diretorio(1, uuid4(), uuid4())
