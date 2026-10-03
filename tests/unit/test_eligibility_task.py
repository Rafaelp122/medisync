"""Unit tests for asynchronous eligibility background task (RF-02, RN03)."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.modules.billing import (
    ElegibilidadeNotifierPort,
    EligibilityProviderPort,
    ResultadoElegibilidade,
    StatusElegibilidade,
)
from src.modules.queue.domain.models import Atendimento, PrioridadeClinica
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.worker.tasks.eligibility import validar_elegibilidade_task


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
async def test_validar_elegibilidade_sus_promotes_attendance_and_enqueues_valkey() -> (
    None
):
    """Under SUS, attendance is promoted to APTO_PARA_CHAMADA and ingested in ZSET."""
    org_id = 1
    atend_id = uuid4()
    paciente_id = uuid4()
    now = datetime.now(UTC)

    mock_atend = MagicMock(spec=Atendimento)
    mock_atend.id = atend_id
    mock_atend.organizacao_id = org_id
    mock_atend.status = StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
    mock_atend.prioridade_clinica = PrioridadeClinica.URGENTE
    mock_atend.data_entrada_fila = now
    mock_atend.criado_em = now

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get.return_value = mock_atend

    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.zadd = AsyncMock(return_value=1)

    ctx = _create_mock_context(mock_session, mock_valkey)

    result = await validar_elegibilidade_task(
        ctx,
        organizacao_id=org_id,
        atendimento_id=str(atend_id),
        paciente_id=str(paciente_id),
        modo_publico_sus=True,
    )

    assert result["status"] == "aprovado"
    assert result["aprovado"] is True
    assert result["codigo_autorizacao"] == "SUS-ISENTO"
    mock_atend.promover_para_apto.assert_called_once()
    mock_session.commit.assert_awaited_once()
    mock_valkey.zadd.assert_awaited_once()


@pytest.mark.asyncio
async def test_validar_elegibilidade_rejection_preserves_status_and_notifies() -> None:
    """When insurance rejects, status is preserved and notifier is alerted (RF-05)."""
    org_id = 2
    atend_id = uuid4()
    paciente_id = uuid4()

    mock_atend = MagicMock(spec=Atendimento)
    mock_atend.id = atend_id
    mock_atend.status = StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get.return_value = mock_atend

    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.zadd = AsyncMock()

    mock_provider = AsyncMock(spec=EligibilityProviderPort)
    mock_provider.verificar_elegibilidade.return_value = ResultadoElegibilidade(
        aprovado=False,
        status=StatusElegibilidade.REJEITADO,
        motivo="Inadimplência financeira",
    )
    mock_notifier = AsyncMock(spec=ElegibilidadeNotifierPort)

    ctx = _create_mock_context(mock_session, mock_valkey)

    result = await validar_elegibilidade_task(
        ctx,
        organizacao_id=org_id,
        atendimento_id=str(atend_id),
        paciente_id=str(paciente_id),
        modo_publico_sus=False,
        provider=mock_provider,
        notifier=mock_notifier,
    )

    assert result["status"] == "REJEITADO"
    assert result["aprovado"] is False
    assert result["motivo"] == "Inadimplência financeira"
    mock_atend.promover_para_apto.assert_not_called()
    mock_session.commit.assert_not_awaited()
    mock_valkey.zadd.assert_not_awaited()
    mock_notifier.notificar_falha.assert_awaited_once()


@pytest.mark.asyncio
async def test_validar_elegibilidade_timeout_preserves_status() -> None:
    """When timeout occurs (15s), attendance is preserved without promotion."""
    org_id = 2
    atend_id = uuid4()
    paciente_id = uuid4()

    mock_atend = MagicMock(spec=Atendimento)
    mock_atend.id = atend_id
    mock_atend.status = StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get.return_value = mock_atend

    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.zadd = AsyncMock()

    mock_provider = AsyncMock(spec=EligibilityProviderPort)
    mock_provider.verificar_elegibilidade.return_value = ResultadoElegibilidade(
        aprovado=False,
        status=StatusElegibilidade.TIMEOUT,
        motivo="Tempo limite de 15s excedido",
    )
    mock_notifier = AsyncMock(spec=ElegibilidadeNotifierPort)

    ctx = _create_mock_context(mock_session, mock_valkey)

    result = await validar_elegibilidade_task(
        ctx,
        organizacao_id=org_id,
        atendimento_id=str(atend_id),
        paciente_id=str(paciente_id),
        modo_publico_sus=False,
        provider=mock_provider,
        notifier=mock_notifier,
    )

    assert result["status"] == "TIMEOUT"
    assert result["aprovado"] is False
    mock_atend.promover_para_apto.assert_not_called()
    mock_session.commit.assert_not_awaited()
    mock_valkey.zadd.assert_not_awaited()
    mock_notifier.notificar_falha.assert_awaited_once()


@pytest.mark.asyncio
async def test_validar_elegibilidade_already_promoted() -> None:
    """If attendance was already promoted to APTO_PARA_CHAMADA, skip promotion."""
    org_id = 1
    atend_id = uuid4()
    paciente_id = uuid4()

    mock_atend = MagicMock(spec=Atendimento)
    mock_atend.id = atend_id
    mock_atend.status = StatusAtendimento.APTO_PARA_CHAMADA.value

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get.return_value = mock_atend

    mock_valkey = MagicMock(spec=Redis)
    ctx = _create_mock_context(mock_session, mock_valkey)

    result = await validar_elegibilidade_task(
        ctx,
        organizacao_id=org_id,
        atendimento_id=str(atend_id),
        paciente_id=str(paciente_id),
        modo_publico_sus=True,
    )

    assert result["status"] == "already_promoted"
    assert result["aprovado"] is True
    mock_atend.promover_para_apto.assert_not_called()
