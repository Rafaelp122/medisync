"""Unit tests for AlocacaoChamadaService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.uuid7 import uuid7
from src.modules.queue.application.dtos import AlocarChamadaCommand
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.domain.exceptions import (
    AtendimentoNaoDisponivelError,
    AtendimentoNaoEncontradoError,
    MedicoOcupadoError,
    TransicaoEstadoInvalidaError,
)
from src.modules.queue.domain.models import Atendimento, StatusAtendimento
from src.modules.queue.infrastructure.lua_loader import LuaScriptManager


@pytest.fixture
def mock_valkey() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_lua_manager() -> AsyncMock:
    return AsyncMock(spec=LuaScriptManager)


@pytest.fixture
def service(
    mock_valkey: AsyncMock,
    mock_session: AsyncMock,
    mock_lua_manager: AsyncMock,
) -> AlocacaoChamadaService:
    return AlocacaoChamadaService(
        valkey=mock_valkey,
        db_session=mock_session,
        lua_manager=mock_lua_manager,
    )


@pytest.mark.asyncio
async def test_alocar_chamada_medico_ocupado_retorna_409(
    service: AlocacaoChamadaService,
    mock_lua_manager: AsyncMock,
) -> None:
    """Verify code 0 from Lua raises MedicoOcupadoError (HTTP 409)."""
    mock_lua_manager.execute_script.return_value = 0

    cmd = AlocarChamadaCommand(
        organizacao_id=1,
        medico_id=uuid4(),
        atendimento_id=uuid7(),
    )

    with pytest.raises(MedicoOcupadoError, match="já possui uma chamada ou consulta"):
        await service.alocar_chamada(cmd)


@pytest.mark.asyncio
async def test_alocar_chamada_atendimento_indisponivel_retorna_409(
    service: AlocacaoChamadaService,
    mock_lua_manager: AsyncMock,
) -> None:
    """Verify code -1 from Lua raises AtendimentoNaoDisponivelError (HTTP 409)."""
    mock_lua_manager.execute_script.return_value = -1

    cmd = AlocarChamadaCommand(
        organizacao_id=1,
        medico_id=uuid4(),
        atendimento_id=uuid7(),
    )

    with pytest.raises(AtendimentoNaoDisponivelError, match="não está disponível"):
        await service.alocar_chamada(cmd)


@pytest.mark.asyncio
async def test_alocar_chamada_sucesso(
    service: AlocacaoChamadaService,
    mock_valkey: AsyncMock,
    mock_session: AsyncMock,
    mock_lua_manager: AsyncMock,
) -> None:
    """Verify code 1 transitions attendance to CHAMANDO_PACIENTE and commits."""
    mock_lua_manager.execute_script.return_value = 1

    atend_id = uuid7()
    med_id = uuid4()
    mock_atendimento = AsyncMock(spec=Atendimento)
    mock_atendimento.id = atend_id
    mock_atendimento.status = StatusAtendimento.CHAMANDO_PACIENTE.value
    mock_atendimento.chamada_iniciada_em = datetime.now(UTC)

    mock_session.get.return_value = mock_atendimento

    cmd = AlocarChamadaCommand(
        organizacao_id=1,
        medico_id=med_id,
        atendimento_id=atend_id,
        ttl_segundos=45,
    )

    result = await service.alocar_chamada(cmd)

    assert result.atendimento_id == atend_id
    assert result.medico_id == med_id
    assert result.status == StatusAtendimento.CHAMANDO_PACIENTE.value
    assert result.ttl_segundos == 45

    mock_atendimento.iniciar_chamada.assert_called_once_with(med_id)
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once_with(mock_atendimento)


@pytest.mark.asyncio
async def test_alocar_chamada_rollback_quando_atendimento_inexistente_no_banco(
    service: AlocacaoChamadaService,
    mock_valkey: AsyncMock,
    mock_session: AsyncMock,
    mock_lua_manager: AsyncMock,
) -> None:
    """Verify locks are released if attendance is not found in DB."""
    mock_lua_manager.execute_script.return_value = 1
    mock_session.get.return_value = None

    atend_id = uuid7()
    med_id = uuid4()

    cmd = AlocarChamadaCommand(
        organizacao_id=99,
        medico_id=med_id,
        atendimento_id=atend_id,
    )

    with pytest.raises(AtendimentoNaoEncontradoError):
        await service.alocar_chamada(cmd)

    # Asserts rollback released both locks in Valkey
    mock_valkey.delete.assert_called_once_with(
        f"lock:99:medico:{med_id}",
        f"lock:99:atendimento:{atend_id}",
    )


@pytest.mark.asyncio
async def test_alocar_chamada_rollback_quando_transicao_invalida(
    service: AlocacaoChamadaService,
    mock_valkey: AsyncMock,
    mock_session: AsyncMock,
    mock_lua_manager: AsyncMock,
) -> None:
    """Verify locks are released if DB entity transition raises error."""
    mock_lua_manager.execute_script.return_value = 1

    atend_id = uuid7()
    med_id = uuid4()
    mock_atendimento = AsyncMock(spec=Atendimento)
    mock_atendimento.iniciar_chamada.side_effect = TransicaoEstadoInvalidaError(
        "Invalid transition"
    )
    mock_session.get.return_value = mock_atendimento

    cmd = AlocarChamadaCommand(
        organizacao_id=1,
        medico_id=med_id,
        atendimento_id=atend_id,
    )

    with pytest.raises(TransicaoEstadoInvalidaError):
        await service.alocar_chamada(cmd)

    mock_valkey.delete.assert_called_once_with(
        f"lock:1:medico:{med_id}",
        f"lock:1:atendimento:{atend_id}",
    )


@pytest.mark.asyncio
async def test_liberar_e_verificar_locks(
    service: AlocacaoChamadaService,
    mock_valkey: AsyncMock,
) -> None:
    """Verify lock query and release helpers."""
    med_id = uuid4()
    atend_id = uuid7()

    await service.liberar_locks(1, med_id, atend_id)
    mock_valkey.delete.assert_called_once_with(
        f"lock:1:medico:{med_id}",
        f"lock:1:atendimento:{atend_id}",
    )

    mock_valkey.exists.return_value = 1
    assert await service.verificar_lock_medico(1, med_id) is True
    mock_valkey.exists.assert_called_with(f"lock:1:medico:{med_id}")

    mock_valkey.exists.return_value = 0
    assert await service.verificar_lock_atendimento(1, atend_id) is False
    mock_valkey.exists.assert_called_with(f"lock:1:atendimento:{atend_id}")

    mock_valkey.get.return_value = str(atend_id)
    retrieved = await service.obter_lock_medico_atendimento_id(1, med_id)
    assert retrieved == str(atend_id)
