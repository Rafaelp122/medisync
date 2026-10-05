"""EvolucaoService blocks edit on terminal attendance."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from src.modules.consultation.application.dtos import RegistrarEvolucaoSOAPCommand
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoResumoDTO,
)
from src.modules.consultation.application.services.evolucao_service import (
    EvolucaoService,
)
from src.modules.consultation.domain.exceptions import ConsultaFinalizadaError


def _make_resumo(is_terminal: bool) -> AtendimentoResumoDTO:
    return AtendimentoResumoDTO(
        atendimento_id=uuid4(),
        organizacao_id=1,
        medico_id=uuid4(),
        status="CONCLUIDO" if is_terminal else "EM_ATENDIMENTO",
        tcle_hash="a" * 64,
        is_terminal=is_terminal,
    )


@pytest.mark.asyncio
async def test_salvar_bloqueia_quando_terminal() -> None:
    session = AsyncMock()
    reader = AsyncMock()
    reader.obter_resumo.return_value = _make_resumo(is_terminal=True)
    svc = EvolucaoService(session=session, reader=reader)
    cmd = RegistrarEvolucaoSOAPCommand(
        atendimento_id=uuid4(),
        organizacao_id=1,
        medico_id=uuid4(),
        anamnese="a",
        conduta="c",
    )
    session.execute.return_value.scalar_one_or_none.return_value = None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result
    with pytest.raises(ConsultaFinalizadaError):
        await svc.salvar_evolucao_soap(cmd)
