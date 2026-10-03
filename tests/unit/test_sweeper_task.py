"""Unit tests for periodic self-healing sweeper task (RN03)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.modules.queue.application.services.fila_service import calcular_score_fila
from src.modules.queue.domain.models import Atendimento, PrioridadeClinica
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.worker.tasks.sweeper import reconciliar_fila_orphans_task


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
async def test_reconciliar_fila_orphans_restores_missing_attendance() -> None:
    """Orphan attendance missing from ZSET with no locks is reinjected."""
    org_id = 1
    atend_id = uuid4()
    now = datetime.now(UTC)
    entrada = now - timedelta(seconds=120)

    mock_atend = MagicMock(spec=Atendimento)
    mock_atend.id = atend_id
    mock_atend.organizacao_id = org_id
    mock_atend.status = StatusAtendimento.APTO_PARA_CHAMADA.value
    mock_atend.prioridade_clinica = PrioridadeClinica.URGENTE
    mock_atend.data_entrada_fila = entrada
    mock_atend.criado_em = entrada
    mock_atend.atualizado_em = entrada
    mock_atend.medico_id = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_atend]

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.return_value = mock_result

    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.zscore = AsyncMock(return_value=None)
    mock_valkey.exists = AsyncMock(return_value=0)
    mock_valkey.zadd = AsyncMock(return_value=1)

    ctx = _create_mock_context(mock_session, mock_valkey)

    result: dict[str, Any] = await reconciliar_fila_orphans_task(
        ctx,
        organizacao_id=org_id,
        threshold_segundos=60,
    )

    assert result["status"] == "success"
    assert result["scanned_organizations"] == 1
    assert result["scanned_appointments"] == 1
    assert result["reconciled_appointments"] == 1
    assert result["reconciled_ids"] == [str(atend_id)]

    expected_score = calcular_score_fila(PrioridadeClinica.URGENTE, entrada)
    mock_valkey.zadd.assert_awaited_once_with(
        f"fila:{org_id}:aptos",
        {str(atend_id): expected_score},
    )


@pytest.mark.asyncio
async def test_reconciliar_fila_orphans_skips_when_already_in_zset() -> None:
    """Attendance already present in Valkey ZSET is not reinjected."""
    org_id = 1
    atend_id = uuid4()
    now = datetime.now(UTC)

    mock_atend = MagicMock(spec=Atendimento)
    mock_atend.id = atend_id
    mock_atend.organizacao_id = org_id
    mock_atend.status = StatusAtendimento.APTO_PARA_CHAMADA.value
    mock_atend.prioridade_clinica = PrioridadeClinica.URGENTE
    mock_atend.data_entrada_fila = now - timedelta(seconds=120)
    mock_atend.criado_em = now - timedelta(seconds=120)
    mock_atend.atualizado_em = now - timedelta(seconds=120)
    mock_atend.medico_id = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_atend]

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.return_value = mock_result

    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.zscore = AsyncMock(return_value=3000000000000)
    mock_valkey.zadd = AsyncMock()

    ctx = _create_mock_context(mock_session, mock_valkey)

    result: dict[str, Any] = await reconciliar_fila_orphans_task(
        ctx,
        organizacao_id=org_id,
        threshold_segundos=60,
    )

    assert result["scanned_appointments"] == 1
    assert result["reconciled_appointments"] == 0
    mock_valkey.zadd.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciliar_fila_orphans_skips_when_ring_lock_active() -> None:
    """Attendance currently in ringing state (lock active) is not reinjected."""
    org_id = 1
    atend_id = uuid4()
    now = datetime.now(UTC)

    mock_atend = MagicMock(spec=Atendimento)
    mock_atend.id = atend_id
    mock_atend.organizacao_id = org_id
    mock_atend.status = StatusAtendimento.APTO_PARA_CHAMADA.value
    mock_atend.prioridade_clinica = PrioridadeClinica.URGENTE
    mock_atend.data_entrada_fila = now - timedelta(seconds=120)
    mock_atend.criado_em = now - timedelta(seconds=120)
    mock_atend.atualizado_em = now - timedelta(seconds=120)
    mock_atend.medico_id = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_atend]

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.return_value = mock_result

    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.zscore = AsyncMock(return_value=None)
    mock_valkey.exists = AsyncMock(return_value=1)
    mock_valkey.zadd = AsyncMock()

    ctx = _create_mock_context(mock_session, mock_valkey)

    result: dict[str, Any] = await reconciliar_fila_orphans_task(
        ctx,
        organizacao_id=org_id,
        threshold_segundos=60,
    )

    assert result["scanned_appointments"] == 1
    assert result["reconciled_appointments"] == 0
    mock_valkey.zadd.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciliar_fila_orphans_skips_when_consultation_lock_active() -> None:
    """Attendance associated with active consultation is not reinjected."""
    org_id = 1
    atend_id = uuid4()
    medico_id = uuid4()
    now = datetime.now(UTC)

    mock_atend = MagicMock(spec=Atendimento)
    mock_atend.id = atend_id
    mock_atend.organizacao_id = org_id
    mock_atend.status = StatusAtendimento.APTO_PARA_CHAMADA.value
    mock_atend.prioridade_clinica = PrioridadeClinica.URGENTE
    mock_atend.data_entrada_fila = now - timedelta(seconds=120)
    mock_atend.criado_em = now - timedelta(seconds=120)
    mock_atend.atualizado_em = now - timedelta(seconds=120)
    mock_atend.medico_id = medico_id

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_atend]

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.return_value = mock_result

    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.zscore = AsyncMock(return_value=None)
    mock_valkey.exists = AsyncMock(return_value=0)
    mock_valkey.get = AsyncMock(return_value=str(atend_id).encode())
    mock_valkey.zadd = AsyncMock()

    ctx = _create_mock_context(mock_session, mock_valkey)

    result: dict[str, Any] = await reconciliar_fila_orphans_task(
        ctx,
        organizacao_id=org_id,
        threshold_segundos=60,
    )

    assert result["scanned_appointments"] == 1
    assert result["reconciled_appointments"] == 0
    mock_valkey.zadd.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciliar_fila_orphans_multi_tenant_discovery() -> None:
    """When organizacao_id is None, sweeper discovers active organizations."""
    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.zscore = AsyncMock(return_value=None)
    mock_valkey.exists = AsyncMock(return_value=0)
    mock_valkey.zadd = AsyncMock(return_value=1)

    mock_session = AsyncMock(spec=AsyncSession)

    # First call: SELECT id FROM organizacoes WHERE ativo = true
    org_result = MagicMock()
    org_result.fetchall.return_value = [(10,), (20,)]

    # Subsequent calls: candidates per org
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [org_result, empty_result, empty_result]

    ctx = _create_mock_context(mock_session, mock_valkey)

    result: dict[str, Any] = await reconciliar_fila_orphans_task(
        ctx,
        organizacao_id=None,
        threshold_segundos=60,
    )

    assert result["status"] == "success"
    assert result["scanned_organizations"] == 2
    assert result["scanned_appointments"] == 0
    assert result["reconciled_appointments"] == 0
