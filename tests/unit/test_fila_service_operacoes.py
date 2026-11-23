"""Unit tests for FilaService operations (position, cancel, deterioration)."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.queue.application.ports.shift_policy_reader_port import ShiftPolicyDTO
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.exceptions import AtendimentoNaoEncontradoError
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.modules.queue.domain.scoring import calcular_score
from src.modules.queue.presentation.schemas import PioraClinicaRequest
from src.modules.triage.application.dtos import TriageRiskEvaluationDTO

from tests.doubles import (
    FakeAsyncSession,
    FakeQueueEngine,
    FakeShiftPolicyReader,
    FakeTriagePort,
)

_SAMPLE_TCLE = "a" * 64


def _default_triage(prioridade: int = 3, *, samu: bool = False) -> FakeTriagePort:
    return FakeTriagePort(
        evaluation=TriageRiskEvaluationDTO(
            prioridade_clinica=prioridade,
            tcle_hash=_SAMPLE_TCLE,
            alerta_samu_disparado=samu,
            instrucao_redirecionamento=(
                "Ligue 192 imediatamente ou procure emergência." if samu else None
            ),
        )
    )


@pytest.mark.asyncio
async def test_obter_posicao_e_estimativa_usa_tma_da_politica() -> None:
    """Estimate uses ShiftPolicyReaderPort TMA and active doctors count."""
    atend_id = uuid4()
    atend = Atendimento(
        id=atend_id,
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=3,
        tcle_hash=_SAMPLE_TCLE,
        data_entrada_fila=datetime.now(UTC),
    )
    engine = FakeQueueEngine(medicos_ativos={uuid4(), uuid4()})
    engine.fila_scores[uuid4()] = 1000
    engine.fila_scores[uuid4()] = 2000
    engine.fila_scores[atend_id] = 3000
    engine.fila_scores[uuid4()] = 4000
    engine.fila_scores[uuid4()] = 5000

    session = FakeAsyncSession(entities={atend_id: atend})
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        shift_policy_reader=FakeShiftPolicyReader(
            ShiftPolicyDTO(tma_padrao_segundos=900)
        ),
    )

    res = await service.obter_posicao_e_estimativa(atendimento_id=atend_id)

    assert res.atendimento_id == atend_id
    assert res.status == StatusAtendimento.APTO_PARA_CHAMADA.value
    assert res.posicao == 3
    assert res.total_aguardando == 5
    # (posicao 3 * 900 TMA) / 2 medicos = 1350s
    assert res.tempo_estimado_segundos == 1350
    assert res.prioridade_clinica == 3
    assert res.chamada_iniciada_em is None
    assert res.ttl_segundos is None


@pytest.mark.asyncio
async def test_obter_posicao_e_estimativa_chamando_expoe_timer_f5() -> None:
    """CHAMANDO_PACIENTE exposes chamada_iniciada_em, ttl_segundos, and priority."""
    chamada_em = datetime.now(UTC) - timedelta(seconds=10)
    atend = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        medico_id=uuid4(),
        status=StatusAtendimento.CHAMANDO_PACIENTE,
        prioridade_clinica=2,
        tcle_hash=_SAMPLE_TCLE,
        chamada_iniciada_em=chamada_em,
    )
    engine = FakeQueueEngine()
    session = FakeAsyncSession(entities={atend.id: atend})
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        shift_policy_reader=FakeShiftPolicyReader(
            ShiftPolicyDTO(tempo_tolerancia_ring_segundos=60)
        ),
    )

    res = await service.obter_posicao_e_estimativa(atendimento_id=atend.id)

    assert res.status == StatusAtendimento.CHAMANDO_PACIENTE.value
    assert res.posicao == 0
    assert res.tempo_estimado_segundos == 0
    assert res.prioridade_clinica == 2
    assert res.chamada_iniciada_em == chamada_em
    assert res.ttl_segundos == 60


@pytest.mark.asyncio
async def test_obter_posicao_e_estimativa_atendimento_nao_encontrado() -> None:
    """Missing attendance raises AtendimentoNaoEncontradoError with offending ID."""
    target_id = uuid4()
    service = FilaService(
        queue_engine=FakeQueueEngine(),
        db_session=cast("AsyncSession", FakeAsyncSession()),
    )

    with pytest.raises(AtendimentoNaoEncontradoError, match=str(target_id)):
        await service.obter_posicao_e_estimativa(atendimento_id=target_id)


@pytest.mark.asyncio
async def test_cancelar_atendimento_paciente_sucesso() -> None:
    """Patient cancellation transitions DB, commits 1x, and removes from ZSET."""
    atend_id = uuid4()
    atend = Atendimento(
        id=atend_id,
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=3,
        tcle_hash=_SAMPLE_TCLE,
        data_entrada_fila=datetime.now(UTC),
    )
    engine = FakeQueueEngine()
    engine.fila_scores[atend_id] = 3000
    session = FakeAsyncSession(entities={atend_id: atend})
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    res = await service.cancelar_atendimento_paciente(
        atendimento_id=atend_id,
        motivo="Melhora dos sintomas",
    )

    assert res.atendimento_id == atend_id
    assert res.status == StatusAtendimento.CANCELADO_PACIENTE.value
    assert res.motivo == "Melhora dos sintomas"
    assert atend.status == StatusAtendimento.CANCELADO_PACIENTE.value
    assert atend_id not in engine.fila_scores
    assert session.commits == 1
    assert session.refreshes == 0


@pytest.mark.asyncio
async def test_cancelar_atendimento_em_chamada_libera_locks_e_notifica_medico() -> None:
    """Cancelling during CHAMANDO_PACIENTE clears ring locks and notifies doctor."""
    med_id = uuid4()
    atend = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        medico_id=med_id,
        status=StatusAtendimento.CHAMANDO_PACIENTE,
        prioridade_clinica=2,
        tcle_hash=_SAMPLE_TCLE,
        chamada_iniciada_em=datetime.now(UTC),
    )
    engine = FakeQueueEngine()
    engine.locks_medico[med_id] = atend.id
    engine.locks_atendimento[atend.id] = med_id
    session = FakeAsyncSession(entities={atend.id: atend})
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    res = await service.cancelar_atendimento_paciente(
        atendimento_id=atend.id,
        motivo="Não posso atender agora",
    )

    assert res.status == StatusAtendimento.CANCELADO_PACIENTE.value
    assert med_id not in engine.locks_medico
    assert atend.id not in engine.locks_atendimento
    assert len(engine.published_medico) == 1
    assert engine.published_medico[0][0] == med_id
    assert engine.published_medico[0][1]["event"] == "CALL_CANCELLED"
    assert engine.published_medico[0][1]["motivo"] == "Não posso atender agora"


@pytest.mark.asyncio
async def test_cancelar_atendimento_falha_commit_nao_muta_valkey() -> None:
    """DB commit failure must leave Valkey ZSET and ring locks completely untouched."""
    med_id = uuid4()
    atend = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        medico_id=med_id,
        status=StatusAtendimento.CHAMANDO_PACIENTE,
        prioridade_clinica=2,
        tcle_hash=_SAMPLE_TCLE,
        chamada_iniciada_em=datetime.now(UTC),
    )
    engine = FakeQueueEngine()
    engine.fila_scores[atend.id] = 2000
    engine.locks_medico[med_id] = atend.id
    engine.locks_atendimento[atend.id] = med_id
    session = FakeAsyncSession(
        entities={atend.id: atend},
        commit_error=RuntimeError("DB unavailable"),
    )
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    with pytest.raises(RuntimeError, match="DB unavailable"):
        await service.cancelar_atendimento_paciente(atend.id, motivo="Teste rollback")

    assert atend.id in engine.fila_scores
    assert engine.locks_medico[med_id] == atend.id
    assert engine.locks_atendimento[atend.id] == med_id
    assert engine.published_medico == []


@pytest.mark.asyncio
async def test_processar_piora_clinica_desvio_samu() -> None:
    """Level 1 deterioration cancels attendance, removes from ZSET, and notifies."""
    med_id = uuid4()
    atend = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        medico_id=med_id,
        status=StatusAtendimento.CHAMANDO_PACIENTE,
        prioridade_clinica=4,
        tcle_hash=_SAMPLE_TCLE,
        data_entrada_fila=datetime.now(UTC),
    )
    engine = FakeQueueEngine()
    engine.fila_scores[atend.id] = 4000
    engine.locks_medico[med_id] = atend.id
    engine.locks_atendimento[atend.id] = med_id
    session = FakeAsyncSession(entities={atend.id: atend})
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        triage_port=_default_triage(prioridade=1, samu=True),
    )

    req = PioraClinicaRequest(
        atendimento_id=atend.id,
        novos_sintomas=["dor_no_peito", "falta_de_ar"],
        escala_dor=9,
        queixa_adicional="Dor intensa irradiando para o braço",
    )

    res = await service.processar_piora_clinica(req)

    assert res.atendimento_id == atend.id
    assert res.prioridade_clinica == 1
    assert res.alerta_samu_disparado is True
    assert res.redirecionado_emergencia is True
    assert res.nova_posicao is None
    assert atend.id not in engine.fila_scores
    assert med_id not in engine.locks_medico
    assert atend.status == StatusAtendimento.CANCELADO_PACIENTE.value
    assert session.commits == 1
    assert len(engine.published_medico) == 1
    assert engine.published_medico[0][1]["event"] == "CALL_CANCELLED"


@pytest.mark.asyncio
async def test_processar_piora_clinica_usa_prioridade_persistida_no_zset() -> None:
    """Reclassification writes ZSET score using persisted priority (no downgrade)."""
    ts_base = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    atend = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=2,  # Already Level 2
        tcle_hash=_SAMPLE_TCLE,
        data_entrada_fila=ts_base,
    )
    engine = FakeQueueEngine()
    engine.fila_scores[atend.id] = calcular_score(2, ts_base)
    session = FakeAsyncSession(entities={atend.id: atend})

    # Triage returns Level 4 (less urgent): persisted priority MUST stay 2
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        triage_port=_default_triage(prioridade=4, samu=False),
    )

    res = await service.processar_piora_clinica(
        PioraClinicaRequest(
            atendimento_id=atend.id,
            novos_sintomas=["coriza"],
            escala_dor=2,
        )
    )

    assert res.prioridade_clinica == 2
    assert atend.prioridade_clinica == 2
    assert engine.fila_scores[atend.id] == calcular_score(2, ts_base)
    assert session.commits == 1


@pytest.mark.asyncio
async def test_processar_piora_clinica_reclassifica_e_protege_commit() -> None:
    """Urgency increase updates ZSET score only after commit succeeds."""
    ts_base = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    atend = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=4,
        tcle_hash=_SAMPLE_TCLE,
        data_entrada_fila=ts_base,
    )
    original_score = calcular_score(4, ts_base)

    # First check rollback on commit error: Valkey must keep original score
    engine_err = FakeQueueEngine()
    engine_err.fila_scores[atend.id] = original_score
    svc_err = FilaService(
        queue_engine=engine_err,
        db_session=cast(
            "AsyncSession",
            FakeAsyncSession(
                entities={atend.id: atend},
                commit_error=RuntimeError("Commit failed"),
            ),
        ),
        triage_port=_default_triage(prioridade=2, samu=False),
    )
    with pytest.raises(RuntimeError, match="Commit failed"):
        await svc_err.processar_piora_clinica(
            PioraClinicaRequest(
                atendimento_id=atend.id,
                novos_sintomas=["cefaleia_intensa"],
                escala_dor=8,
            )
        )
    assert engine_err.fila_scores[atend.id] == original_score

    # Now commit succeeds on fresh entity: score updates to priority 2
    atend_ok = Atendimento(
        id=atend.id,
        paciente_id=atend.paciente_id,
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=4,
        tcle_hash=_SAMPLE_TCLE,
        data_entrada_fila=ts_base,
    )
    engine_ok = FakeQueueEngine()
    engine_ok.fila_scores[atend_ok.id] = original_score
    session_ok = FakeAsyncSession(entities={atend_ok.id: atend_ok})
    svc_ok = FilaService(
        queue_engine=engine_ok,
        db_session=cast("AsyncSession", session_ok),
        triage_port=_default_triage(prioridade=2, samu=False),
    )
    res = await svc_ok.processar_piora_clinica(
        PioraClinicaRequest(
            atendimento_id=atend_ok.id,
            novos_sintomas=["cefaleia_intensa"],
            escala_dor=8,
        )
    )
    assert res.prioridade_clinica == 2
    assert res.alerta_samu_disparado is False
    assert res.redirecionado_emergencia is False
    assert engine_ok.fila_scores[atend_ok.id] == calcular_score(2, ts_base)
    assert session_ok.commits == 1
