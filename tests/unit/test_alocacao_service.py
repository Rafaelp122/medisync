"""Unit tests for AlocacaoChamadaService (Lua 4-Keys, rollback, ARQ compensation)."""

import logging
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from arq.connections import ArqRedis
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
from src.modules.queue.domain.scoring import calcular_score

from tests.doubles import (
    FakeArqPool,
    FakeAsyncSession,
    FakeAuditTrail,
    FakeQueueEngine,
)

_SAMPLE_TCLE = "a" * 64


@pytest.mark.asyncio
async def test_alocar_chamada_medico_ocupado_por_ring_ou_consulta_ativa() -> None:
    """Doctor with active ring or active consultation lock raises MedicoOcupadoError."""
    med_id = uuid4()
    atend_id = uuid7()
    session = FakeAsyncSession()

    # Case 1: Active ring lock (KEYS[1])
    engine_ring = FakeQueueEngine()
    engine_ring.fila_scores[atend_id] = 1000
    engine_ring.locks_medico[med_id] = uuid7()
    svc_ring = AlocacaoChamadaService(
        queue_engine=engine_ring,
        db_session=cast("AsyncSession", session),
    )
    with pytest.raises(MedicoOcupadoError, match="já possui uma chamada ou consulta"):
        await svc_ring.alocar_chamada(
            AlocarChamadaCommand(medico_id=med_id, atendimento_id=atend_id)
        )

    # Case 2: Active consultation lock (KEYS[4] - 4-Keys anti-overbooking)
    engine_consulta = FakeQueueEngine()
    engine_consulta.fila_scores[atend_id] = 1000
    engine_consulta.locks_consulta_ativa[med_id] = uuid7()
    svc_consulta = AlocacaoChamadaService(
        queue_engine=engine_consulta,
        db_session=cast("AsyncSession", session),
    )
    with pytest.raises(MedicoOcupadoError, match="já possui uma chamada ou consulta"):
        await svc_consulta.alocar_chamada(
            AlocarChamadaCommand(medico_id=med_id, atendimento_id=atend_id)
        )


@pytest.mark.asyncio
async def test_alocar_chamada_atendimento_indisponivel_retorna_409() -> None:
    """Missing or already locked attendance raises AtendimentoNaoDisponivelError."""
    engine = FakeQueueEngine()
    session = FakeAsyncSession()
    service = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    cmd = AlocarChamadaCommand(medico_id=uuid4(), atendimento_id=uuid7())
    with pytest.raises(AtendimentoNaoDisponivelError, match="não está disponível"):
        await service.alocar_chamada(cmd)


@pytest.mark.asyncio
async def test_alocar_chamada_sucesso_publica_eventos_e_nao_faz_refresh() -> None:
    """Successful allocation transitions status, commits 1x, and publishes Pub/Sub."""
    med_id = uuid4()
    pac_id = uuid4()
    atendimento = Atendimento(
        id=uuid7(),
        paciente_id=pac_id,
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=2,
        tcle_hash=_SAMPLE_TCLE,
    )
    atend_id = atendimento.id
    engine = FakeQueueEngine()
    engine.fila_scores[atend_id] = calcular_score(2, atendimento.criado_em)
    session = FakeAsyncSession(entities={atend_id: atendimento})
    audit = FakeAuditTrail()
    arq_pool = FakeArqPool()

    service = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        arq_pool=cast("ArqRedis", arq_pool),
        audit_trail=audit,
    )

    result = await service.alocar_chamada(
        AlocarChamadaCommand(
            medico_id=med_id,
            atendimento_id=atend_id,
            ttl_segundos=45,
        )
    )

    assert result.atendimento_id == atend_id
    assert result.medico_id == med_id
    assert result.status == StatusAtendimento.CHAMANDO_PACIENTE.value
    assert result.ttl_segundos == 45
    assert result.paciente_id == pac_id
    assert result.prioridade_clinica == 2
    assert session.commits == 1
    assert session.refreshes == 0
    assert session.get_calls[-1]["with_for_update"] is True
    assert len(arq_pool.enqueued_jobs) == 1
    assert arq_pool.enqueued_jobs[0]["function"] == "resolver_ring_timeout_task"

    assert len(engine.published_medico) == 1
    assert engine.published_medico[0][0] == med_id
    assert engine.published_medico[0][1]["event"] == "INCOMING_CALL"
    assert len(engine.published_fila) == 1
    assert engine.published_fila[0][0] == atend_id
    assert engine.published_fila[0][1]["event"] == "CALLED"


@pytest.mark.asyncio
async def test_alocar_proximo_pula_candidato_travado_e_checa_consulta_ativa() -> None:
    """alocar_proximo_paciente skips locked candidates and blocks active lock."""
    med_id = uuid4()
    atend_1 = Atendimento(
        id=uuid7(),
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=1,
        tcle_hash=_SAMPLE_TCLE,
    )
    atend_2 = Atendimento(
        id=uuid7(),
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=2,
        tcle_hash=_SAMPLE_TCLE,
    )
    engine = FakeQueueEngine()
    engine.fila_scores[atend_1.id] = 1_000_000_000_001
    engine.fila_scores[atend_2.id] = 2_000_000_000_002
    engine.locks_atendimento[atend_1.id] = uuid4()

    session = FakeAsyncSession(entities={atend_2.id: atend_2})
    service = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    result = await service.alocar_proximo_paciente(medico_id=med_id)
    assert result is not None
    assert result.atendimento_id == atend_2.id
    assert engine.locks_medico[med_id] == atend_2.id

    # Doctor now locked by ring; clear ring and set active consultation lock -> 409
    await engine.liberar_ring(med_id, atend_2.id)
    engine.locks_consulta_ativa[med_id] = atend_2.id
    with pytest.raises(MedicoOcupadoError):
        await service.alocar_proximo_paciente(medico_id=med_id)


@pytest.mark.asyncio
async def test_alocar_proximo_paciente_fila_vazia_retorna_none() -> None:
    """Empty queue returns None without hitting DB."""
    engine = FakeQueueEngine()
    session = FakeAsyncSession()
    service = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    assert await service.alocar_proximo_paciente(medico_id=uuid4()) is None
    assert len(session.get_calls) == 0


@pytest.mark.asyncio
async def test_alocar_chamada_rollback_quando_atendimento_inexistente() -> None:
    """Missing attendance in DB rolls back and clears ring locks."""
    med_id = uuid4()
    atend_id = uuid7()
    engine = FakeQueueEngine()
    engine.fila_scores[atend_id] = 1000
    session = FakeAsyncSession()
    service = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    with pytest.raises(AtendimentoNaoEncontradoError):
        await service.alocar_chamada(
            AlocarChamadaCommand(medico_id=med_id, atendimento_id=atend_id)
        )

    assert session.rollbacks == 1
    assert med_id not in engine.locks_medico
    assert atend_id not in engine.locks_atendimento


@pytest.mark.asyncio
async def test_alocar_chamada_rollback_devolve_atendimento_apto_para_zset() -> None:
    """DB commit failure on APTO attendance returns it to ZSET and clears ring locks."""
    med_id = uuid4()
    atendimento = Atendimento(
        id=uuid7(),
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=2,
        tcle_hash=_SAMPLE_TCLE,
    )
    atend_id = atendimento.id
    ts_base = atendimento.data_entrada_fila or atendimento.criado_em
    expected_score = calcular_score(2, ts_base)

    engine = FakeQueueEngine()
    engine.fila_scores[atend_id] = expected_score
    session = FakeAsyncSession(
        entities={atend_id: atendimento},
        commit_error=RuntimeError("DB commit failed"),
    )
    service = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    with pytest.raises(RuntimeError, match="DB commit failed"):
        await service.alocar_chamada(
            AlocarChamadaCommand(medico_id=med_id, atendimento_id=atend_id)
        )

    assert session.rollbacks == 1
    assert med_id not in engine.locks_medico
    assert atend_id not in engine.locks_atendimento
    assert engine.fila_scores.get(atend_id) == expected_score


@pytest.mark.asyncio
async def test_alocar_chamada_rollback_quando_transicao_invalida() -> None:
    """Invalid state transition rolls back DB and clears ring locks."""
    med_id = uuid4()
    atendimento = Atendimento(
        id=uuid7(),
        paciente_id=uuid4(),
        status=StatusAtendimento.CONCLUIDO,
        prioridade_clinica=3,
        tcle_hash=_SAMPLE_TCLE,
    )
    atend_id = atendimento.id
    engine = FakeQueueEngine()
    engine.fila_scores[atend_id] = 3000
    session = FakeAsyncSession(entities={atend_id: atendimento})
    service = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    with pytest.raises(TransicaoEstadoInvalidaError):
        await service.alocar_chamada(
            AlocarChamadaCommand(medico_id=med_id, atendimento_id=atend_id)
        )

    assert session.rollbacks == 1
    assert med_id not in engine.locks_medico
    assert atend_id not in engine.locks_atendimento
    assert atend_id not in engine.fila_scores


@pytest.mark.asyncio
async def test_alocar_chamada_falha_enqueue_arq_reverte_estado_e_devolve_zset(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ARQ enqueue failure reverts attendance to APTO_PARA_CHAMADA and restores ZSET."""
    med_id = uuid4()
    atendimento = Atendimento(
        id=uuid7(),
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=2,
        tcle_hash=_SAMPLE_TCLE,
    )
    atend_id = atendimento.id
    ts_base = atendimento.data_entrada_fila or atendimento.criado_em
    expected_score = calcular_score(2, ts_base)

    engine = FakeQueueEngine()
    engine.fila_scores[atend_id] = expected_score
    session = FakeAsyncSession(entities={atend_id: atendimento})
    failing_arq = FakeArqPool(error=ConnectionError("Valkey ARQ unavailable"))

    service = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        arq_pool=cast("ArqRedis", failing_arq),
    )

    with (
        caplog.at_level(logging.CRITICAL),
        pytest.raises(ConnectionError, match="Valkey ARQ unavailable"),
    ):
        await service.alocar_chamada(
            AlocarChamadaCommand(medico_id=med_id, atendimento_id=atend_id)
        )

    assert atendimento.status == StatusAtendimento.APTO_PARA_CHAMADA.value
    assert atendimento.medico_id is None
    assert session.commits == 2
    assert med_id not in engine.locks_medico
    assert atend_id not in engine.locks_atendimento
    assert engine.fila_scores.get(atend_id) == expected_score
    assert "resolver_ring_timeout_task" in caplog.text
