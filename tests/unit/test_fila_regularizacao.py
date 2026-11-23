"""Unit tests for attendance eligibility regularization in queue (US-05 / NC-QUE-04).

Regras: RN01 (Score Imutável de Antiguidade), RN03 (Preservação de Antiguidade).
Especificação: docs/user-stories/US-05-regularizacao-elegibilidade-fila.md
"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError, ValidationError
from src.modules.queue.application.dtos import RegularizacaoFilaCommand
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.exceptions import TransicaoEstadoInvalidaError
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)
from src.modules.queue.domain.scoring import calcular_score

from tests.doubles import FakeAsyncSession, FakeAuditTrail, FakeQueueEngine


@pytest.mark.asyncio
async def test_regularizar_contingencia_sucesso_restaura_score_original_no_valkey() -> (
    None
):
    """Paciente regularizado restaura score original com antiguidade justa (RN01, RN03).

    Regras: RN01 (Score Imutável), RN03 (Preservação de Antiguidade), NC-QUE-04.
    História: docs/user-stories/US-05-regularizacao-elegibilidade-fila.md
    """
    now = datetime.now(UTC)
    t0 = now - timedelta(minutes=30)
    t1 = now - timedelta(minutes=5)

    paciente_1 = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="a" * 64,
        criado_em=t0,
        data_entrada_fila=t0,
    )
    paciente_2 = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        criado_em=t1,
        data_entrada_fila=t1,
    )

    engine = FakeQueueEngine()
    engine.fila_scores[paciente_2.id] = calcular_score(
        paciente_2.prioridade_clinica, t1
    )

    fake_session = FakeAsyncSession(
        entities={paciente_1.id: paciente_1, paciente_2.id: paciente_2}
    )
    fila_service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", fake_session),
    )

    cmd = RegularizacaoFilaCommand(
        atendimento_id=paciente_1.id,
        tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
        motivo="Indisponibilidade gateway operadora",
    )

    result = await fila_service.regularizar_atendimento(cmd)

    assert result.promovido is True
    assert result.status == StatusAtendimento.APTO_PARA_CHAMADA.value

    score_p1 = engine.fila_scores.get(paciente_1.id)
    score_p2 = engine.fila_scores.get(paciente_2.id)
    assert score_p1 is not None
    assert score_p2 is not None
    assert score_p1 < score_p2

    rank_p1, _ = await engine.obter_posicao_e_tamanho(paciente_1.id)
    assert rank_p1 == 0


@pytest.mark.asyncio
async def test_regularizar_idempotencia_duplo_acionamento() -> None:
    """Segunda regularização para atendimento já apto é idempotente (sem mutação)."""
    now = datetime.now(UTC)
    t0 = now - timedelta(minutes=20)

    paciente = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        criado_em=t0,
        data_entrada_fila=t0,
    )

    engine = FakeQueueEngine()
    score_original = calcular_score(paciente.prioridade_clinica, t0)
    engine.fila_scores[paciente.id] = score_original

    fake_session = FakeAsyncSession(entities={paciente.id: paciente})
    fila_service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", fake_session),
    )

    cmd = RegularizacaoFilaCommand(
        atendimento_id=paciente.id,
        tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
        motivo="Segunda regularização redundante",
    )

    result = await fila_service.regularizar_atendimento(cmd)

    assert result.promovido is False
    assert result.status == "already_promoted"
    assert engine.fila_scores[paciente.id] == score_original


@pytest.mark.asyncio
async def test_regularizar_atendimento_inexistente() -> None:
    """Tentativa de regularizar atendimento inexistente lança NotFoundError."""
    fila_service = FilaService(
        queue_engine=FakeQueueEngine(),
        db_session=cast("AsyncSession", FakeAsyncSession()),
    )

    inexistente_id = uuid4()
    cmd_inexistente = RegularizacaoFilaCommand(
        atendimento_id=inexistente_id,
        tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
        motivo="Tentativa de regularizar atendimento inexistente",
    )
    with pytest.raises(NotFoundError) as exc_inexistente:
        await fila_service.regularizar_atendimento(cmd_inexistente)

    assert str(inexistente_id) in str(exc_inexistente.value)


@pytest.mark.asyncio
async def test_regularizar_status_invalido_rejeita_com_offending_value() -> None:
    """Status incompatível é rejeitado com mensagem contendo o valor ofensivo."""
    paciente_em_atendimento = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        status=StatusAtendimento.EM_ATENDIMENTO,
        prioridade_clinica=PrioridadeClinica.URGENTE,
    )

    fake_session = FakeAsyncSession(
        entities={paciente_em_atendimento.id: paciente_em_atendimento}
    )
    fila_service = FilaService(
        queue_engine=FakeQueueEngine(),
        db_session=cast("AsyncSession", fake_session),
    )

    cmd = RegularizacaoFilaCommand(
        atendimento_id=paciente_em_atendimento.id,
        tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
        motivo="Tentativa de regularizar atendimento já em consulta médica",
    )

    with pytest.raises(TransicaoEstadoInvalidaError) as exc_info:
        await fila_service.regularizar_atendimento(cmd)

    assert StatusAtendimento.EM_ATENDIMENTO.value in str(exc_info.value)


@pytest.mark.asyncio
async def test_regularizar_motivo_vazio_lanca_validation_error() -> None:
    """Motivo vazio ou apenas espaços em branco rejeita com ValidationError."""
    paciente = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
    )

    fake_session = FakeAsyncSession(entities={paciente.id: paciente})
    fila_service = FilaService(
        queue_engine=FakeQueueEngine(),
        db_session=cast("AsyncSession", fake_session),
    )

    for motivo_invalido in ["", "   ", "\t  \n"]:
        with pytest.raises(ValidationError):
            cmd = RegularizacaoFilaCommand(
                atendimento_id=paciente.id,
                tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
                motivo=motivo_invalido,
            )
            await fila_service.regularizar_atendimento(cmd)


@pytest.mark.asyncio
async def test_regularizar_contingencia_promove_e_insere_fila() -> None:
    """Regularização assistencial promove atendimento para APTO e insere no ZSET."""
    paciente = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="a" * 64,
    )

    engine = FakeQueueEngine()
    fake_session = FakeAsyncSession(entities={paciente.id: paciente})
    fila_service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", fake_session),
    )

    cmd = RegularizacaoFilaCommand(
        atendimento_id=paciente.id,
        tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
        motivo="Liberação assistencial imediata pelo acolhimento SUS",
    )

    result = await fila_service.regularizar_atendimento(cmd)

    assert result.promovido is True
    assert result.status == StatusAtendimento.APTO_PARA_CHAMADA.value
    assert paciente.status == StatusAtendimento.APTO_PARA_CHAMADA.value
    assert paciente.id in engine.fila_scores


@pytest.mark.asyncio
async def test_regularizar_atendimento_registra_audit_trail_sem_refresh() -> None:
    """Record ELEGIBILIDADE_CONFIRMADA before commit without refresh."""
    paciente = Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="b" * 64,
    )
    fake_session = FakeAsyncSession(entities={paciente.id: paciente})
    audit = FakeAuditTrail()

    fila_service = FilaService(
        queue_engine=FakeQueueEngine(),
        db_session=cast("AsyncSession", fake_session),
        audit_trail=audit,
    )

    await fila_service.regularizar_atendimento(
        RegularizacaoFilaCommand(
            atendimento_id=paciente.id,
            tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
            motivo="Paciente regularizou documento no acolhimento",
        )
    )

    events = audit.get_events_by_type("ELEGIBILIDADE_CONFIRMADA")
    assert len(events) == 1
    assert events[0]["atendimento_id"] == paciente.id
    assert events[0]["payload"]["tipo_contingencia"] == "CONTINGENCIA_ASSISTENCIAL"
    assert events[0]["estado_anterior"] == "TRIADO_AGUARDANDO_ELEGIBILIDADE"
    assert events[0]["novo_estado"] == "APTO_PARA_CHAMADA"
    assert fake_session.commits == 1
    assert fake_session.refreshes == 0
