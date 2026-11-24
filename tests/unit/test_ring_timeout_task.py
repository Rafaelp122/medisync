"""Unit tests for deterministic 45s ring timeout task and no-show resolution (RN02)."""

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from arq.connections import ArqRedis
    from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.queue.application.dtos import AlocarChamadaCommand
from src.modules.queue.application.ports import (
    LoggingPacienteAusenteNotifier,
    PacienteAusenteEvent,
)
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.worker.tasks.ring_timeout import resolver_ring_timeout_task

from tests.doubles import (
    FakeArqPool,
    FakeAsyncSession,
    FakeAsyncSessionFactory,
    FakePacienteAusenteNotifier,
    FakeQueueEngine,
    FakeValkey,
)

_SAMPLE_TCLE = "a" * 64


def _create_worker_context(
    session: FakeAsyncSession,
    valkey: FakeValkey,
) -> dict[str, Any]:
    return {
        "db_session_factory": FakeAsyncSessionFactory(session),
        "valkey_client": valkey,
    }


@pytest.mark.asyncio
async def test_resolver_ring_timeout_records_no_show_when_chamando_paciente() -> None:
    """If patient did not answer in 45s, mark absent, release locks and emit event."""
    medico_id = uuid4()
    paciente_id = uuid4()
    atendimento = Atendimento(
        id=uuid4(),
        paciente_id=paciente_id,
        medico_id=medico_id,
        status=StatusAtendimento.CHAMANDO_PACIENTE,
        tcle_hash=_SAMPLE_TCLE,
    )
    atend_id = atendimento.id

    fake_session = FakeAsyncSession(entities={atend_id: atendimento})
    fake_valkey = FakeValkey()
    await fake_valkey.set(f"lock:medico:{medico_id}", str(atend_id))
    await fake_valkey.set(f"lock:atendimento:{atend_id}", str(medico_id))

    notifier = FakePacienteAusenteNotifier()
    ctx = _create_worker_context(fake_session, fake_valkey)

    result: dict[str, Any] = await resolver_ring_timeout_task(
        ctx,
        atendimento_id=str(atend_id),
        medico_id=str(medico_id),
        notifier=notifier,
    )

    assert result["status"] == "resolved"
    assert result["action"] == "no_show_recorded"
    assert atendimento.status == StatusAtendimento.PACIENTE_AUSENTE.value
    assert fake_session.commits == 1

    assert await fake_valkey.exists(f"lock:medico:{medico_id}") == 0
    assert await fake_valkey.exists(f"lock:atendimento:{atend_id}") == 0

    assert len(notifier.events) == 1
    emitted_event = notifier.events[0]
    assert emitted_event.atendimento_id == atend_id
    assert emitted_event.medico_id == medico_id
    assert emitted_event.paciente_id == paciente_id
    assert emitted_event.tempo_toque_segundos == 45


@pytest.mark.asyncio
async def test_resolver_ring_timeout_promotes_lock_when_em_atendimento() -> None:
    """If call is answered, preserve consultation and set active consultation lock."""
    medico_id = uuid4()
    atendimento = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        medico_id=medico_id,
        status=StatusAtendimento.EM_ATENDIMENTO,
        tcle_hash=_SAMPLE_TCLE,
    )
    atend_id = atendimento.id

    fake_session = FakeAsyncSession(entities={atend_id: atendimento})
    fake_valkey = FakeValkey()
    await fake_valkey.set(f"lock:medico:{medico_id}", str(atend_id))
    await fake_valkey.set(f"lock:atendimento:{atend_id}", str(medico_id))

    notifier = FakePacienteAusenteNotifier()
    ctx = _create_worker_context(fake_session, fake_valkey)

    result: dict[str, Any] = await resolver_ring_timeout_task(
        ctx,
        atendimento_id=str(atend_id),
        medico_id=str(medico_id),
        notifier=notifier,
    )

    assert result["status"] == "resolved"
    assert result["action"] == "active_consultation_preserved"
    assert atendimento.status == StatusAtendimento.EM_ATENDIMENTO.value
    assert fake_session.commits == 0

    assert await fake_valkey.exists(f"lock:atendimento:{atend_id}") == 0
    assert await fake_valkey.exists(f"lock:medico:{medico_id}") == 0
    assert await fake_valkey.get(f"lock:consulta_ativa:medico:{medico_id}") == str(
        atend_id
    )
    assert len(notifier.events) == 0


@pytest.mark.asyncio
async def test_resolver_ring_timeout_attendance_not_found() -> None:
    """If attendance is missing in DB, gracefully ignore."""
    ctx = _create_worker_context(FakeAsyncSession(), FakeValkey())

    result: dict[str, Any] = await resolver_ring_timeout_task(
        ctx,
        atendimento_id=str(uuid4()),
        medico_id=str(uuid4()),
    )

    assert result["status"] == "not_found"
    assert result["action"] == "ignored"


@pytest.mark.asyncio
async def test_resolver_ring_timeout_terminal_state_releases_locks() -> None:
    """If attendance is already cancelled/finished, cleanup lingering ring locks."""
    medico_id = uuid4()
    atendimento = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        medico_id=medico_id,
        status=StatusAtendimento.CANCELADO_PACIENTE,
        tcle_hash=_SAMPLE_TCLE,
    )
    atend_id = atendimento.id

    fake_session = FakeAsyncSession(entities={atend_id: atendimento})
    fake_valkey = FakeValkey()
    await fake_valkey.set(f"lock:medico:{medico_id}", str(atend_id))
    await fake_valkey.set(f"lock:atendimento:{atend_id}", str(medico_id))

    ctx = _create_worker_context(fake_session, fake_valkey)

    result: dict[str, Any] = await resolver_ring_timeout_task(
        ctx,
        atendimento_id=str(atend_id),
        medico_id=str(medico_id),
    )

    assert result["status"] == "resolved"
    assert result["action"] == "already_finalized"
    assert await fake_valkey.exists(f"lock:medico:{medico_id}") == 0
    assert await fake_valkey.exists(f"lock:atendimento:{atend_id}") == 0


@pytest.mark.asyncio
async def test_logging_paciente_ausente_notifier(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """LoggingPacienteAusenteNotifier logs structured warning."""
    notifier = LoggingPacienteAusenteNotifier()
    event = PacienteAusenteEvent(
        atendimento_id=uuid4(),
        medico_id=uuid4(),
        paciente_id=uuid4(),
    )
    with caplog.at_level(logging.WARNING):
        await notifier.emitir_paciente_ausente(event)

    assert str(event.atendimento_id) in caplog.text


@pytest.mark.asyncio
async def test_alocacao_service_schedules_arq_job() -> None:
    """AlocacaoChamadaService enqueues resolver_ring_timeout_task when arq_pool set."""
    medico_id = uuid4()
    atendimento = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        tcle_hash=_SAMPLE_TCLE,
    )
    atend_id = atendimento.id

    engine = FakeQueueEngine()
    engine.fila_scores[atend_id] = 5000
    session = FakeAsyncSession(entities={atend_id: atendimento})
    arq_pool = FakeArqPool()

    service = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        arq_pool=cast("ArqRedis", arq_pool),
    )

    cmd = AlocarChamadaCommand(
        medico_id=medico_id,
        atendimento_id=atend_id,
        ttl_segundos=45,
    )

    result = await service.alocar_chamada(cmd)
    assert result.atendimento_id == atend_id
    assert len(arq_pool.enqueued_jobs) == 1
    job = arq_pool.enqueued_jobs[0]
    assert job["function"] == "resolver_ring_timeout_task"
    assert job["kwargs"] == {
        "atendimento_id": str(atend_id),
        "medico_id": str(medico_id),
        "_defer_by": timedelta(seconds=45),
        "_job_id": f"ring_timeout:{atend_id}",
    }
