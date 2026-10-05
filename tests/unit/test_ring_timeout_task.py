"""Unit tests for deterministic 45s ring timeout task and no-show resolution (RN02)."""

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.modules.queue.application.dtos import AlocarChamadaCommand
from src.modules.queue.application.ports import (
    LoggingPacienteAusenteNotifier,
    PacienteAusenteEvent,
    PacienteAusenteNotifierPort,
)
from src.modules.queue.application.ports.allocation_port import (
    AllocationPort,
    AlocacaoCodigo,
)
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.worker.tasks.ring_timeout import resolver_ring_timeout_task


def _create_mock_context(
    mock_session: AsyncMock, mock_valkey: MagicMock
) -> dict[str, Any]:
    mock_factory = MagicMock(spec=async_sessionmaker)
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    return {
        "db_session_factory": mock_factory,
        "valkey_client": mock_valkey,
    }


@pytest.mark.asyncio
async def test_resolver_ring_timeout_records_no_show_when_chamando_paciente() -> None:
    """If patient did not answer in 45s, mark absent, release locks and emit event."""
    org_id = 1
    atend_id = uuid4()
    medico_id = uuid4()
    paciente_id = uuid4()

    mock_atendimento = MagicMock(spec=Atendimento)
    mock_atendimento.id = atend_id
    mock_atendimento.organizacao_id = org_id
    mock_atendimento.paciente_id = paciente_id
    mock_atendimento.medico_id = medico_id
    mock_atendimento.status = StatusAtendimento.CHAMANDO_PACIENTE.value

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get.return_value = mock_atendimento

    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock()
    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.pipeline.return_value.__aenter__.return_value = mock_pipe

    mock_notifier = AsyncMock(spec=PacienteAusenteNotifierPort)
    ctx = _create_mock_context(mock_session, mock_valkey)

    result: dict[str, Any] = await resolver_ring_timeout_task(
        ctx,
        organizacao_id=org_id,
        atendimento_id=str(atend_id),
        medico_id=str(medico_id),
        notifier=mock_notifier,
    )

    assert result["status"] == "resolved"
    assert result["action"] == "no_show_recorded"
    mock_atendimento.registrar_ausencia_paciente.assert_called_once()
    mock_session.commit.assert_awaited_once()

    # Valkey ring locks deleted atomically
    mock_pipe.delete.assert_any_call(f"lock:{org_id}:medico:{medico_id}")
    mock_pipe.delete.assert_any_call(f"lock:{org_id}:atendimento:{atend_id}")
    mock_pipe.execute.assert_awaited_once()

    # Domain event emitted
    mock_notifier.emitir_paciente_ausente.assert_awaited_once()
    emitted_event: PacienteAusenteEvent = (
        mock_notifier.emitir_paciente_ausente.call_args[0][0]
    )
    assert emitted_event.atendimento_id == atend_id
    assert emitted_event.medico_id == medico_id
    assert emitted_event.paciente_id == paciente_id
    assert emitted_event.tempo_toque_segundos == 45


@pytest.mark.asyncio
async def test_resolver_ring_timeout_promotes_lock_when_em_atendimento() -> None:
    """If call is answered, preserve consultation and set active consultation lock."""
    org_id = 1
    atend_id = uuid4()
    medico_id = uuid4()

    mock_atendimento = MagicMock(spec=Atendimento)
    mock_atendimento.id = atend_id
    mock_atendimento.status = StatusAtendimento.EM_ATENDIMENTO.value

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get.return_value = mock_atendimento

    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock()
    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.pipeline.return_value.__aenter__.return_value = mock_pipe

    mock_notifier = AsyncMock(spec=PacienteAusenteNotifierPort)
    ctx = _create_mock_context(mock_session, mock_valkey)

    result: dict[str, Any] = await resolver_ring_timeout_task(
        ctx,
        organizacao_id=org_id,
        atendimento_id=str(atend_id),
        medico_id=str(medico_id),
        notifier=mock_notifier,
    )

    assert result["status"] == "resolved"
    assert result["action"] == "active_consultation_preserved"
    mock_atendimento.registrar_ausencia_paciente.assert_not_called()
    mock_session.commit.assert_not_awaited()

    # Ring locks deleted and consulta_ativa lock set with 2h TTL
    mock_pipe.delete.assert_any_call(f"lock:{org_id}:atendimento:{atend_id}")
    mock_pipe.delete.assert_any_call(f"lock:{org_id}:medico:{medico_id}")
    mock_pipe.set.assert_called_once_with(
        f"lock:{org_id}:consulta_ativa:medico:{medico_id}",
        str(atend_id),
        ex=7200,
    )
    mock_pipe.execute.assert_awaited_once()
    mock_notifier.emitir_paciente_ausente.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolver_ring_timeout_attendance_not_found() -> None:
    """If attendance is missing in DB, gracefully ignore."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get.return_value = None

    mock_valkey = MagicMock(spec=Redis)
    ctx = _create_mock_context(mock_session, mock_valkey)

    result: dict[str, Any] = await resolver_ring_timeout_task(
        ctx,
        organizacao_id=1,
        atendimento_id=str(uuid4()),
        medico_id=str(uuid4()),
    )

    assert result["status"] == "not_found"
    assert result["action"] == "ignored"


@pytest.mark.asyncio
async def test_resolver_ring_timeout_terminal_state_releases_locks() -> None:
    """If attendance is already cancelled/finished, cleanup lingering ring locks."""
    org_id = 2
    atend_id = uuid4()
    medico_id = uuid4()

    mock_atendimento = MagicMock(spec=Atendimento)
    mock_atendimento.id = atend_id
    mock_atendimento.status = StatusAtendimento.CANCELADO_PACIENTE.value

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get.return_value = mock_atendimento

    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock()
    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.pipeline.return_value.__aenter__.return_value = mock_pipe

    ctx = _create_mock_context(mock_session, mock_valkey)

    result: dict[str, Any] = await resolver_ring_timeout_task(
        ctx,
        organizacao_id=org_id,
        atendimento_id=str(atend_id),
        medico_id=str(medico_id),
    )

    assert result["status"] == "resolved"
    assert result["action"] == "already_finalized"
    mock_pipe.delete.assert_any_call(f"lock:{org_id}:medico:{medico_id}")
    mock_pipe.delete.assert_any_call(f"lock:{org_id}:atendimento:{atend_id}")
    mock_pipe.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_logging_paciente_ausente_notifier() -> None:
    """LoggingPacienteAusenteNotifier logs structured warning."""
    notifier = LoggingPacienteAusenteNotifier()
    event = PacienteAusenteEvent(
        atendimento_id=uuid4(),
        organizacao_id=1,
        medico_id=uuid4(),
        paciente_id=uuid4(),
    )
    with patch(
        "src.modules.queue.application.ports.paciente_ausente_notifier.logger.warning"
    ) as mock_log:
        await notifier.emitir_paciente_ausente(event)

    mock_log.assert_called_once()
    assert "Event %s" in str(mock_log.call_args[0][0])


@pytest.mark.asyncio
async def test_alocacao_service_schedules_arq_job() -> None:
    """AlocacaoChamadaService enqueues resolver_ring_timeout_task
    when arq_pool is set.
    """
    mock_valkey = AsyncMock(spec=Redis)
    mock_session = AsyncMock(spec=AsyncSession)
    mock_lua = AsyncMock(spec=AllocationPort)
    mock_lua.alocar_chamada.return_value = AlocacaoCodigo.SUCESSO

    atend_id = uuid4()
    medico_id = uuid4()

    mock_atendimento = MagicMock(spec=Atendimento)
    mock_atendimento.id = atend_id
    mock_atendimento.status = StatusAtendimento.CHAMANDO_PACIENTE.value
    mock_atendimento.chamada_iniciada_em = None
    mock_session.get.return_value = mock_atendimento

    mock_arq_pool = AsyncMock()

    service = AlocacaoChamadaService(
        valkey=mock_valkey,
        db_session=mock_session,
        lua_manager=mock_lua,
        arq_pool=mock_arq_pool,
    )

    cmd = AlocarChamadaCommand(
        organizacao_id=1,
        medico_id=medico_id,
        atendimento_id=atend_id,
        ttl_segundos=45,
    )

    result = await service.alocar_chamada(cmd)
    assert result.atendimento_id == atend_id

    mock_arq_pool.enqueue_job.assert_awaited_once_with(
        "resolver_ring_timeout_task",
        organizacao_id=1,
        atendimento_id=str(atend_id),
        medico_id=str(medico_id),
        _defer_by=timedelta(seconds=45),
        _job_id=f"ring_timeout:{atend_id}",
    )
