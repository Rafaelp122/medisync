"""Unit tests for queue ingestion service, 64-bit scoring, and atomic scan."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import ValidationError
from src.core.uuid7 import uuid7
from src.modules.queue.application.dtos import (
    AdquirirProximoPacienteCommand,
    IngressarFilaCommand,
)
from src.modules.queue.application.ports.shift_policy_reader_port import ShiftPolicyDTO
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.exceptions import (
    AtendimentoNaoEncontradoError,
    MedicoOcupadoError,
    TransicaoEstadoInvalidaError,
)
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)
from src.modules.queue.domain.scoring import calcular_score

from tests.doubles import (
    FakeAsyncSession,
    FakeQueueEngine,
    FakeShiftPolicyReader,
)

_SAMPLE_TCLE = "a" * 64


def test_calcular_score_formula() -> None:
    """Validate 64-bit score formula: (priority * 10^12) + timestamp."""
    epoch_fixed = 1_700_000_000
    assert (
        calcular_score(PrioridadeClinica.EMERGENCIA, epoch_fixed) == 1_001_700_000_000
    )
    assert (
        calcular_score(PrioridadeClinica.MUITO_URGENTE, epoch_fixed)
        == 2_001_700_000_000
    )
    assert (
        calcular_score(PrioridadeClinica.POUCO_URGENTE, epoch_fixed)
        == 4_001_700_000_000
    )
    assert (
        calcular_score(PrioridadeClinica.NAO_URGENTE, epoch_fixed) == 5_001_700_000_000
    )

    dt = datetime.fromtimestamp(epoch_fixed, tz=UTC)
    assert calcular_score(PrioridadeClinica.URGENTE, dt) == 3_001_700_000_000

    score_default = calcular_score(PrioridadeClinica.URGENTE)
    assert 3_000_000_000_000 < score_default < 4_000_000_000_000


def test_calcular_score_invalid_priority() -> None:
    """Invalid priorities outside [1, 5] must raise ValidationError."""
    with pytest.raises(ValidationError):
        calcular_score(0)

    with pytest.raises(ValidationError):
        calcular_score(6)


def test_prevalencia_clinica_invariante_rn01() -> None:
    """Clinical urgency must mathematically precede lower urgency (RN01)."""
    now = datetime.now(UTC)
    ten_years_ago = now - timedelta(days=3650)

    score_lvl2_now = calcular_score(PrioridadeClinica.MUITO_URGENTE, now)
    score_lvl4_old = calcular_score(PrioridadeClinica.POUCO_URGENTE, ten_years_ago)
    assert score_lvl2_now < score_lvl4_old


@pytest.mark.asyncio
async def test_ingressar_fila_unit() -> None:
    """Ingress attendance and verify QueueEnginePort score and 1-based position."""
    engine = FakeQueueEngine()
    session = FakeAsyncSession()
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )
    atend_id = uuid4()
    cmd = IngressarFilaCommand(
        atendimento_id=atend_id,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        data_entrada_fila=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )

    result = await service.ingressar_fila(cmd)

    assert result.atendimento_id == atend_id
    assert result.posicao == 1
    assert atend_id in engine.fila_scores


@pytest.mark.asyncio
async def test_adquirir_proximo_paciente_fila_vazia() -> None:
    """Return None when queue has no patients and still register active doctor."""
    engine = FakeQueueEngine()
    session = FakeAsyncSession()
    alocacao = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        alocacao_service=alocacao,
    )
    med_id = uuid4()
    result = await service.adquirir_proximo_paciente(
        AdquirirProximoPacienteCommand(medico_id=med_id)
    )
    assert result is None
    assert med_id in engine.medicos_ativos


@pytest.mark.asyncio
async def test_adquirir_proximo_paciente_sucesso_com_ttl_da_politica() -> None:
    """Allocate top patient using ShiftPolicyDTO ring tolerance when TTL omitted."""
    atend = Atendimento(
        id=uuid7(),
        paciente_id=uuid7(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash=_SAMPLE_TCLE,
    )
    medico_id = uuid4()
    engine = FakeQueueEngine()
    engine.fila_scores[atend.id] = 3000
    session = FakeAsyncSession(entities={atend.id: atend})
    alocacao = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        alocacao_service=alocacao,
        shift_policy_reader=FakeShiftPolicyReader(
            ShiftPolicyDTO(tempo_tolerancia_ring_segundos=60)
        ),
    )

    result = await service.adquirir_proximo_paciente(
        AdquirirProximoPacienteCommand(medico_id=medico_id)
    )
    assert result is not None
    assert result.atendimento_id == atend.id
    assert result.ttl_segundos == 60
    assert medico_id in engine.medicos_ativos
    assert engine.alocar_proximo_calls[-1]["ttl_segundos"] == 60


@pytest.mark.asyncio
async def test_adquirir_proximo_paciente_medico_ocupado() -> None:
    """Busy doctor (ring or active consultation) raises MedicoOcupadoError."""
    medico_id = uuid4()
    engine = FakeQueueEngine()
    engine.locks_consulta_ativa[medico_id] = uuid7()
    session = FakeAsyncSession()
    alocacao = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        alocacao_service=alocacao,
    )

    with pytest.raises(MedicoOcupadoError):
        await service.adquirir_proximo_paciente(
            AdquirirProximoPacienteCommand(medico_id=medico_id)
        )


@pytest.mark.asyncio
async def test_adquirir_proximo_paciente_zrange_pula_travado() -> None:
    """Atomic scan skips locked candidate and allocates next free patient."""
    atend_1 = Atendimento(
        id=uuid7(),
        paciente_id=uuid7(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash=_SAMPLE_TCLE,
    )
    atend_2 = Atendimento(
        id=uuid7(),
        paciente_id=uuid7(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash=_SAMPLE_TCLE,
    )
    engine = FakeQueueEngine()
    engine.fila_scores[atend_1.id] = 1000
    engine.fila_scores[atend_2.id] = 2000
    engine.locks_atendimento[atend_1.id] = uuid4()

    session = FakeAsyncSession(entities={atend_2.id: atend_2})
    alocacao = AlocacaoChamadaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        alocacao_service=alocacao,
    )

    result = await service.adquirir_proximo_paciente(
        AdquirirProximoPacienteCommand(medico_id=uuid4(), max_scan=50)
    )
    assert result is not None
    assert result.atendimento_id == atend_2.id
    assert len(engine.alocar_proximo_calls) == 1


@pytest.mark.asyncio
async def test_remover_e_obter_posicao_e_tamanho() -> None:
    """Test helper queue query and removal methods."""
    engine = FakeQueueEngine()
    id_1, id_2, id_3 = uuid4(), uuid4(), uuid4()
    engine.fila_scores[id_1] = 1000
    engine.fila_scores[id_2] = 2000
    engine.fila_scores[id_3] = 3000

    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", FakeAsyncSession()),
    )

    assert await service.obter_posicao_fila(id_2) == 2
    assert await service.obter_tamanho_fila() == 3
    assert await service.remover_da_fila(id_2) is True
    assert await service.obter_posicao_fila(id_2) is None
    assert await service.obter_tamanho_fila() == 2


@pytest.mark.asyncio
async def test_atender_chamada_success_transitions_state_and_locks() -> None:
    """Transition from CHAMANDO_PACIENTE to EM_ATENDIMENTO with lock promotion."""
    paciente_id = uuid7()
    medico_id = uuid7()
    atendimento = Atendimento(
        paciente_id=paciente_id,
        tcle_hash=_SAMPLE_TCLE,
    )
    atendimento.promover_para_apto()
    atendimento.iniciar_chamada(medico_id=medico_id)

    engine = FakeQueueEngine()
    engine.locks_medico[medico_id] = atendimento.id
    engine.locks_atendimento[atendimento.id] = medico_id
    session = FakeAsyncSession(entities={atendimento.id: atendimento})
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    await service.atender_chamada(atendimento.id)

    assert session.get_calls[-1]["with_for_update"] is True
    assert atendimento.status == StatusAtendimento.EM_ATENDIMENTO.value
    assert session.commits == 1
    assert medico_id not in engine.locks_medico
    assert atendimento.id not in engine.locks_atendimento
    assert engine.locks_consulta_ativa[medico_id] == atendimento.id


@pytest.mark.asyncio
async def test_atender_chamada_idempotent_when_already_em_atendimento() -> None:
    """Refreshes active consultation lock without committing when already active."""
    paciente_id = uuid7()
    medico_id = uuid7()
    atendimento = Atendimento(
        paciente_id=paciente_id,
        tcle_hash=_SAMPLE_TCLE,
    )
    atendimento.promover_para_apto()
    atendimento.iniciar_chamada(medico_id=medico_id)
    atendimento.atender_chamada()

    engine = FakeQueueEngine()
    session = FakeAsyncSession(entities={atendimento.id: atendimento})
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    await service.atender_chamada(atendimento.id)

    assert session.get_calls[-1]["with_for_update"] is True
    assert session.commits == 0
    assert engine.locks_consulta_ativa[medico_id] == atendimento.id


@pytest.mark.asyncio
async def test_atender_chamada_invalid_status_raises_conflict() -> None:
    """Cannot directly answer attendance in APTO_PARA_CHAMADA."""
    atendimento = Atendimento(
        paciente_id=uuid7(),
        tcle_hash=_SAMPLE_TCLE,
    )
    atendimento.promover_para_apto()
    session = FakeAsyncSession(entities={atendimento.id: atendimento})
    service = FilaService(
        queue_engine=FakeQueueEngine(),
        db_session=cast("AsyncSession", session),
    )

    with pytest.raises(TransicaoEstadoInvalidaError, match="Apenas atendimentos em"):
        await service.atender_chamada(atendimento.id)

    assert session.get_calls[-1]["with_for_update"] is True


@pytest.mark.asyncio
async def test_atender_chamada_not_found_raises_404() -> None:
    """Non-existent attendance raises AtendimentoNaoEncontradoError."""
    session = FakeAsyncSession()
    service = FilaService(
        queue_engine=FakeQueueEngine(),
        db_session=cast("AsyncSession", session),
    )

    target_id = uuid4()
    with pytest.raises(AtendimentoNaoEncontradoError, match=str(target_id)):
        await service.atender_chamada(target_id)

    assert session.get_calls[-1]["with_for_update"] is True


@pytest.mark.asyncio
async def test_resolver_ring_timeout_with_for_update_no_show() -> None:
    """Validate with_for_update=True and no-show transition when CHAMANDO_PACIENTE."""
    medico_id = uuid7()
    atendimento = Atendimento(
        paciente_id=uuid7(),
        tcle_hash=_SAMPLE_TCLE,
    )
    atendimento.promover_para_apto()
    atendimento.iniciar_chamada(medico_id=medico_id)

    engine = FakeQueueEngine()
    engine.locks_medico[medico_id] = atendimento.id
    engine.locks_atendimento[atendimento.id] = medico_id
    session = FakeAsyncSession(entities={atendimento.id: atendimento})
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    res = await service.resolver_ring_timeout(
        atendimento_id=atendimento.id,
        medico_id=medico_id,
    )

    assert res == "no_show_recorded"
    assert session.get_calls[-1]["with_for_update"] is True
    assert atendimento.status == StatusAtendimento.PACIENTE_AUSENTE.value
    assert session.commits == 1
    assert medico_id not in engine.locks_medico


@pytest.mark.asyncio
async def test_resolver_ring_timeout_with_for_update_active_consultation() -> None:
    """Validate with_for_update=True and active lock promotion when EM_ATENDIMENTO."""
    medico_id = uuid7()
    atendimento = Atendimento(
        paciente_id=uuid7(),
        tcle_hash=_SAMPLE_TCLE,
    )
    atendimento.promover_para_apto()
    atendimento.iniciar_chamada(medico_id=medico_id)
    atendimento.atender_chamada()

    engine = FakeQueueEngine()
    session = FakeAsyncSession(entities={atendimento.id: atendimento})
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
    )

    res = await service.resolver_ring_timeout(
        atendimento_id=atendimento.id,
        medico_id=medico_id,
    )

    assert res == "active_consultation_preserved"
    assert session.get_calls[-1]["with_for_update"] is True
    assert engine.locks_consulta_ativa[medico_id] == atendimento.id


@pytest.mark.asyncio
async def test_resolver_ring_timeout_with_for_update_not_found() -> None:
    """Validate with_for_update=True when attendance not found."""
    session = FakeAsyncSession()
    service = FilaService(
        queue_engine=FakeQueueEngine(),
        db_session=cast("AsyncSession", session),
    )

    target_id = uuid4()
    res = await service.resolver_ring_timeout(
        atendimento_id=target_id,
        medico_id=uuid4(),
    )

    assert res == "not_found"
    assert session.get_calls[-1]["with_for_update"] is True
