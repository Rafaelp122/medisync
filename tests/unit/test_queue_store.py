"""Unit tests for FilaService QueueStorePort implementations (Fase 3)."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.queue.application.ports.queue_store_port import (
    AdmissaoAptoResult,
    AtendimentoSnapshotDTO,
    QueueStorePort,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.exceptions import AtendimentoNaoEncontradoError
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import (
    PrioridadeClinica,
    StatusAtendimento,
)

from tests.doubles import FakeAsyncSession, FakeQueueEngine, FakeResult

_SAMPLE_TCLE = "a" * 64


def test_fila_service_satisfies_queue_store_port() -> None:
    svc = FilaService(
        queue_engine=FakeQueueEngine(),
        db_session=cast("AsyncSession", FakeAsyncSession()),
    )
    assert isinstance(svc, QueueStorePort)


@pytest.mark.asyncio
async def test_admitir_atendimento_apto_success() -> None:
    atend = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash=_SAMPLE_TCLE,
        data_entrada_fila=datetime.now(UTC),
    )
    engine = FakeQueueEngine()
    session = FakeAsyncSession(entities={atend.id: atend})
    svc = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    res = await svc.admitir_atendimento_apto(atend.id)
    assert isinstance(res, AdmissaoAptoResult)
    assert res.promovido is True
    assert res.status == "aprovado"
    assert atend.status == StatusAtendimento.APTO_PARA_CHAMADA.value
    assert session.commits == 1
    assert atend.id in engine.fila_scores


@pytest.mark.asyncio
async def test_admitir_atendimento_apto_not_found() -> None:
    svc = FilaService(
        queue_engine=FakeQueueEngine(),
        db_session=cast("AsyncSession", FakeAsyncSession()),
    )
    missing_id = uuid4()
    with pytest.raises(AtendimentoNaoEncontradoError, match=str(missing_id)):
        await svc.admitir_atendimento_apto(missing_id)


@pytest.mark.asyncio
async def test_resolver_ring_timeout_no_show() -> None:
    med_id = uuid4()
    atend = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        medico_id=med_id,
        status=StatusAtendimento.CHAMANDO_PACIENTE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash=_SAMPLE_TCLE,
    )
    engine = FakeQueueEngine()
    engine.locks_medico[med_id] = atend.id
    engine.locks_atendimento[atend.id] = med_id
    session = FakeAsyncSession(entities={atend.id: atend})
    svc = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    action = await svc.resolver_ring_timeout(atend.id, med_id)
    assert action == "no_show_recorded"
    assert atend.status == StatusAtendimento.PACIENTE_AUSENTE.value
    assert session.commits == 1
    assert med_id not in engine.locks_medico
    assert atend.id not in engine.locks_atendimento


@pytest.mark.asyncio
async def test_concluir_atendimento_auto_commit_true_libera_lock_consulta() -> None:
    med_id = uuid4()
    atend = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        medico_id=med_id,
        status=StatusAtendimento.EM_ATENDIMENTO,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash=_SAMPLE_TCLE,
    )
    engine = FakeQueueEngine()
    engine.locks_consulta_ativa[med_id] = atend.id
    session = FakeAsyncSession(entities={atend.id: atend})
    svc = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    returned_med = await svc.concluir_atendimento(atend.id)
    assert returned_med == med_id
    assert atend.status == StatusAtendimento.CONCLUIDO.value
    assert session.commits == 1
    assert session.get_calls[-1]["with_for_update"] is True
    assert med_id not in engine.locks_consulta_ativa


@pytest.mark.asyncio
async def test_concluir_atendimento_auto_commit_false_flushes_sem_commitar() -> None:
    """auto_commit=False flushes and retains active consultation lock until release."""
    med_id = uuid4()
    atend = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        medico_id=med_id,
        status=StatusAtendimento.EM_ATENDIMENTO,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash=_SAMPLE_TCLE,
    )
    engine = FakeQueueEngine()
    engine.locks_consulta_ativa[med_id] = atend.id
    session = FakeAsyncSession(entities={atend.id: atend})
    svc = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    returned_med = await svc.concluir_atendimento(atend.id, auto_commit=False)
    assert returned_med == med_id
    assert atend.status == StatusAtendimento.CONCLUIDO.value
    assert session.commits == 0
    assert session.flushes == 1
    assert med_id in engine.locks_consulta_ativa

    await svc.liberar_consulta_ativa_medico(med_id)
    assert med_id not in engine.locks_consulta_ativa


@pytest.mark.asyncio
async def test_buscar_atendimento() -> None:
    atend = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        status=StatusAtendimento.CONCLUIDO,
        prioridade_clinica=PrioridadeClinica.POUCO_URGENTE,
        tcle_hash=_SAMPLE_TCLE,
        data_entrada_fila=datetime.now(UTC),
    )
    session = FakeAsyncSession(results=[FakeResult(atend)])
    svc = FilaService(
        queue_engine=FakeQueueEngine(),
        db_session=cast("AsyncSession", session),
    )

    snapshot = await svc.buscar_atendimento(atend.id)
    assert isinstance(snapshot, AtendimentoSnapshotDTO)
    assert snapshot.id == atend.id
    assert snapshot.status == StatusAtendimento.CONCLUIDO.value
    assert snapshot.is_terminal is True
