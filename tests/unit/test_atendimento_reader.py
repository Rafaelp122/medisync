"""AtendimentoReaderPort returns DTO, None when missing, maps terminal statuses."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.consultation.infrastructure.atendimento_reader_sql import (
    SqlAtendimentoReader,
)


@pytest.mark.asyncio
async def test_reader_mapeia_terminal() -> None:
    session = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.mappings.return_value.one_or_none.return_value = {
        "id": uuid4(),
        "organizacao_id": 1,
        "medico_id": uuid4(),
        "status": "CONCLUIDO",
        "tcle_hash": "a" * 64,
    }
    session.execute.return_value = mock_res
    reader = SqlAtendimentoReader(session)
    dto = await reader.obter_resumo(uuid4())
    assert dto is not None and dto.is_terminal is True


@pytest.mark.asyncio
async def test_reader_nao_terminal_e_none_quando_ausente() -> None:
    session = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    atend_id = uuid4()
    medico_id = uuid4()
    mock_res.mappings.return_value.one_or_none.side_effect = [
        {
            "id": atend_id,
            "organizacao_id": 2,
            "medico_id": medico_id,
            "status": "EM_ATENDIMENTO",
            "tcle_hash": None,
        },
        None,
    ]
    session.execute.return_value = mock_res
    reader = SqlAtendimentoReader(session)

    dto = await reader.obter_resumo(atend_id)
    assert dto is not None
    assert dto.is_terminal is False
    assert dto.status == "EM_ATENDIMENTO"
    assert dto.medico_id == medico_id
    assert dto.organizacao_id == 2

    assert await reader.obter_resumo(uuid4()) is None
