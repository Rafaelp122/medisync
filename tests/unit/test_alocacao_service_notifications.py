"""Unit tests verifying notification integration and non-blocking failure
semantics in AlocacaoChamadaService.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.notifications import LoggingNotificationAdapter, NotificationPort
from src.core.uuid7 import uuid7
from src.modules.queue.application.dtos import AlocarChamadaCommand
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
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


@pytest.mark.asyncio
async def test_alocacao_dispatches_notification_when_phone_provided(
    mock_valkey: AsyncMock,
    mock_session: AsyncMock,
    mock_lua_manager: AsyncMock,
) -> None:
    """Verify that call allocation dispatches a WhatsApp notification to the patient."""
    mock_lua_manager.execute_script.return_value = 1

    atend_id = uuid7()
    med_id = uuid4()
    mock_atendimento = AsyncMock(spec=Atendimento)
    mock_atendimento.id = atend_id
    mock_atendimento.status = StatusAtendimento.CHAMANDO_PACIENTE.value
    mock_atendimento.chamada_iniciada_em = datetime.now(UTC)
    mock_session.get.return_value = mock_atendimento

    fake_notifier = LoggingNotificationAdapter()
    service = AlocacaoChamadaService(
        valkey=mock_valkey,
        db_session=mock_session,
        lua_manager=mock_lua_manager,
        notification_adapter=fake_notifier,
    )

    phone = "+5511999991111"
    cmd = AlocarChamadaCommand(
        organizacao_id=1,
        medico_id=med_id,
        atendimento_id=atend_id,
        ttl_segundos=45,
        telefone_paciente=phone,
    )

    result = await service.alocar_chamada(cmd)

    # 1. Allocation succeeded
    assert result.atendimento_id == atend_id
    assert result.status == StatusAtendimento.CHAMANDO_PACIENTE.value
    mock_atendimento.iniciar_chamada.assert_called_once_with(med_id)
    mock_session.commit.assert_called_once()

    # 2. Notification was sent
    assert len(fake_notifier.sent_whatsapp) == 1
    sent = fake_notifier.sent_whatsapp[0]
    assert sent["to"] == phone
    assert sent["template"] == "chamada_consulta"
    assert sent["params"]["atendimento_id"] == str(atend_id)
    assert sent["params"]["medico_id"] == str(med_id)


@pytest.mark.asyncio
async def test_message_failure_does_not_block_queue_progression(
    mock_valkey: AsyncMock,
    mock_session: AsyncMock,
    mock_lua_manager: AsyncMock,
) -> None:
    """Verify Criterion 3: Message failures do NOT block transactional
    queue progression.

    Even if the notification provider raises an exception (e.g. network down),
    the allocation transaction commits, locks remain in Valkey, and result is returned.
    """

    mock_lua_manager.execute_script.return_value = 1

    atend_id = uuid7()
    med_id = uuid4()
    mock_atendimento = AsyncMock(spec=Atendimento)
    mock_atendimento.id = atend_id
    mock_atendimento.status = StatusAtendimento.CHAMANDO_PACIENTE.value
    mock_atendimento.chamada_iniciada_em = datetime.now(UTC)
    mock_session.get.return_value = mock_atendimento

    # Create a failing notification adapter that raises an unhandled error
    failing_notifier = AsyncMock(spec=NotificationPort)
    failing_notifier.send_whatsapp.side_effect = RuntimeError(
        "WhatsApp Cloud API network timeout 504 Gateway Error"
    )

    service = AlocacaoChamadaService(
        valkey=mock_valkey,
        db_session=mock_session,
        lua_manager=mock_lua_manager,
        notification_adapter=failing_notifier,
    )

    cmd = AlocarChamadaCommand(
        organizacao_id=1,
        medico_id=med_id,
        atendimento_id=atend_id,
        ttl_segundos=45,
        telefone_paciente="+5511988882222",
    )

    # Must NOT raise RuntimeError, progression continues unaffected
    result = await service.alocar_chamada(cmd)

    assert result.atendimento_id == atend_id
    assert result.status == StatusAtendimento.CHAMANDO_PACIENTE.value
    # DB session was committed and not rolled back
    mock_session.commit.assert_called_once()
    # Notification was attempted
    failing_notifier.send_whatsapp.assert_called_once()


@pytest.mark.asyncio
async def test_rate_limited_notification_does_not_block_queue_progression(
    mock_valkey: AsyncMock,
    mock_session: AsyncMock,
    mock_lua_manager: AsyncMock,
) -> None:
    """Verify that a rate-limited notification (returning False)
    does not impede call allocation.
    """

    mock_lua_manager.execute_script.return_value = 1

    atend_id = uuid7()
    med_id = uuid4()
    mock_atendimento = AsyncMock(spec=Atendimento)
    mock_atendimento.id = atend_id
    mock_atendimento.status = StatusAtendimento.CHAMANDO_PACIENTE.value
    mock_atendimento.chamada_iniciada_em = datetime.now(UTC)
    mock_session.get.return_value = mock_atendimento

    rate_limited_notifier = AsyncMock(spec=NotificationPort)
    rate_limited_notifier.send_whatsapp.return_value = False  # Rate limited

    service = AlocacaoChamadaService(
        valkey=mock_valkey,
        db_session=mock_session,
        lua_manager=mock_lua_manager,
        notification_adapter=rate_limited_notifier,
    )

    cmd = AlocarChamadaCommand(
        organizacao_id=1,
        medico_id=med_id,
        atendimento_id=atend_id,
        ttl_segundos=45,
        telefone_paciente="+5511977773333",
    )

    result = await service.alocar_chamada(cmd)

    assert result.atendimento_id == atend_id
    assert result.status == StatusAtendimento.CHAMANDO_PACIENTE.value
    mock_session.commit.assert_called_once()
    rate_limited_notifier.send_whatsapp.assert_called_once()
