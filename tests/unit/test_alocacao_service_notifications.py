"""Unit tests verifying notification integration and non-blocking failure
semantics in AlocacaoChamadaService.
"""

from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.uuid7 import uuid7
from src.modules.queue.application.dtos import AlocarChamadaCommand
from src.modules.queue.application.ports.notification_port import NotificationPort
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.domain.models import Atendimento, StatusAtendimento
from src.modules.queue.infrastructure.notifications import LoggingNotificationAdapter

from tests.doubles import FakeAsyncSession, FakeQueueEngine

_SAMPLE_TCLE = "a" * 64


class FailingNotificationAdapter(NotificationPort):
    """Named fake notification adapter raising a simulated gateway timeout."""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls: int = 0

    async def send_whatsapp(
        self,
        to: str,
        template: str,
        params: dict[str, str] | None = None,
    ) -> bool:
        self.calls += 1
        raise self._error


class RateLimitedNotificationAdapter(NotificationPort):
    """Named fake notification adapter simulating rate-limited delivery."""

    def __init__(self) -> None:
        self.calls: int = 0

    async def send_whatsapp(
        self,
        to: str,
        template: str,
        params: dict[str, str] | None = None,
    ) -> bool:
        self.calls += 1
        return False


def _setup_apto_attendance() -> tuple[Atendimento, FakeQueueEngine, FakeAsyncSession]:
    atendimento = Atendimento(
        id=uuid7(),
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=2,
        tcle_hash=_SAMPLE_TCLE,
    )
    engine = FakeQueueEngine()
    engine.fila_scores[atendimento.id] = 2000
    session = FakeAsyncSession(entities={atendimento.id: atendimento})
    return atendimento, engine, session


@pytest.mark.asyncio
async def test_alocacao_dispatches_notification_when_phone_provided() -> None:
    """Verify that call allocation dispatches a WhatsApp notification to patient."""
    atendimento, engine, session = _setup_apto_attendance()
    med_id = uuid4()
    fake_notifier = LoggingNotificationAdapter()

    service = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        notification_adapter=fake_notifier,
    )

    phone = "+5511999991111"
    cmd = AlocarChamadaCommand(
        medico_id=med_id,
        atendimento_id=atendimento.id,
        ttl_segundos=45,
        telefone_paciente=phone,
    )

    result = await service.alocar_chamada(cmd)

    assert result.atendimento_id == atendimento.id
    assert result.status == StatusAtendimento.CHAMANDO_PACIENTE.value
    assert session.commits == 1

    assert len(fake_notifier.sent_whatsapp) == 1
    sent = fake_notifier.sent_whatsapp[0]
    assert sent["to"] == phone
    assert sent["template"] == "chamada_consulta"
    params = cast("dict[str, str]", sent["params"])
    assert params["atendimento_id"] == str(atendimento.id)
    assert params["medico_id"] == str(med_id)


@pytest.mark.asyncio
async def test_message_failure_does_not_block_queue_progression() -> None:
    """Message failures do NOT block transactional queue progression."""
    atendimento, engine, session = _setup_apto_attendance()
    med_id = uuid4()
    failing_notifier = FailingNotificationAdapter(
        RuntimeError("WhatsApp Cloud API network timeout 504 Gateway Error")
    )

    service = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        notification_adapter=failing_notifier,
    )

    cmd = AlocarChamadaCommand(
        medico_id=med_id,
        atendimento_id=atendimento.id,
        ttl_segundos=45,
        telefone_paciente="+5511988882222",
    )

    result = await service.alocar_chamada(cmd)

    assert result.atendimento_id == atendimento.id
    assert result.status == StatusAtendimento.CHAMANDO_PACIENTE.value
    assert session.commits == 1
    assert session.rollbacks == 0
    assert failing_notifier.calls == 1


@pytest.mark.asyncio
async def test_rate_limited_notification_does_not_block_queue_progression() -> None:
    """Rate-limited notification (returning False) does not impede call allocation."""
    atendimento, engine, session = _setup_apto_attendance()
    med_id = uuid4()
    rate_limited_notifier = RateLimitedNotificationAdapter()

    service = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        notification_adapter=rate_limited_notifier,
    )

    cmd = AlocarChamadaCommand(
        medico_id=med_id,
        atendimento_id=atendimento.id,
        ttl_segundos=45,
        telefone_paciente="+5511977773333",
    )

    result = await service.alocar_chamada(cmd)

    assert result.atendimento_id == atendimento.id
    assert result.status == StatusAtendimento.CHAMANDO_PACIENTE.value
    assert session.commits == 1
    assert rate_limited_notifier.calls == 1
