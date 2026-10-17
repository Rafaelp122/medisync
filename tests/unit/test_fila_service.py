"""Unit tests for queue ingestion service, 64-bit scoring, and retry loop (RN01)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from src.core.errors import NotFoundError, ValidationError
from src.core.uuid7 import uuid7
from src.modules.queue.application.dtos import (
    AdquirirProximoPacienteCommand,
    AlocacaoChamadaResult,
    IngressarFilaCommand,
)
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.fila_service import (
    FilaService,
)
from src.modules.queue.domain.exceptions import (
    AtendimentoNaoDisponivelError,
    MedicoOcupadoError,
    TransicaoEstadoInvalidaError,
)
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)
from src.modules.queue.domain.scoring import calcular_score


def test_calcular_score_formula() -> None:
    """Validate 64-bit score formula: (priority * 10^12) + timestamp."""
    epoch_fixed = 1_700_000_000
    score_p1 = calcular_score(PrioridadeClinica.EMERGENCIA, epoch_fixed)
    assert score_p1 == 1_001_700_000_000

    score_p2 = calcular_score(PrioridadeClinica.MUITO_URGENTE, epoch_fixed)
    assert score_p2 == 2_001_700_000_000

    score_p4 = calcular_score(PrioridadeClinica.POUCO_URGENTE, epoch_fixed)
    assert score_p4 == 4_001_700_000_000

    score_p5 = calcular_score(PrioridadeClinica.NAO_URGENTE, epoch_fixed)
    assert score_p5 == 5_001_700_000_000

    # With datetime instance
    dt = datetime.fromtimestamp(epoch_fixed, tz=UTC)
    assert calcular_score(PrioridadeClinica.URGENTE, dt) == 3_001_700_000_000

    # With default timestamp (current time)
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

    # A level 2 patient who arrived right now
    score_lvl2_now = calcular_score(PrioridadeClinica.MUITO_URGENTE, now)

    # A level 4 patient who waited for 10 years
    score_lvl4_old = calcular_score(PrioridadeClinica.POUCO_URGENTE, ten_years_ago)

    # Level 2 must have a LOWER score than level 4 (ZSET sorts ascending)
    assert score_lvl2_now < score_lvl4_old


@pytest.mark.asyncio
async def test_ingressar_fila_unit() -> None:
    """Ingress attendance and verify Valkey ZADD and ZRANK invocation."""
    mock_valkey = AsyncMock()
    mock_session = AsyncMock()
    mock_valkey.zadd.return_value = 1
    mock_valkey.zrank.return_value = 0  # 0-indexed rank -> position 1

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=AsyncMock(),
    )
    atend_id = uuid4()
    cmd = IngressarFilaCommand(
        organizacao_id=1,
        atendimento_id=atend_id,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        data_entrada_fila=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )

    result = await service.ingressar_fila(cmd)

    assert result.atendimento_id == atend_id
    assert result.organizacao_id == 1
    assert result.posicao == 1
    mock_valkey.zadd.assert_called_once()
    mock_valkey.zrank.assert_called_once_with("fila:1:aptos", str(atend_id))


@pytest.mark.asyncio
async def test_adquirir_proximo_paciente_fila_vazia() -> None:
    """Return None when queue has no patients waiting."""
    mock_valkey = AsyncMock()
    mock_session = AsyncMock()
    mock_valkey.zrange.return_value = []

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=AsyncMock(),
    )
    cmd = AdquirirProximoPacienteCommand(organizacao_id=1, medico_id=uuid4())

    result = await service.adquirir_proximo_paciente(cmd)
    assert result is None


@pytest.mark.asyncio
async def test_adquirir_proximo_paciente_sucesso_primeira_tentativa() -> None:
    """Successfully allocate the top patient in queue on first attempt."""
    mock_valkey = AsyncMock()
    mock_session = AsyncMock()
    mock_alocacao = AsyncMock(spec=AlocacaoChamadaService)

    atend_id = uuid4()
    medico_id = uuid4()
    mock_valkey.zrange.return_value = [str(atend_id)]

    expected_result = AlocacaoChamadaResult(
        atendimento_id=atend_id,
        medico_id=medico_id,
        status=StatusAtendimento.CHAMANDO_PACIENTE,
        chamada_iniciada_em=datetime.now(UTC),
        ttl_segundos=45,
    )
    mock_alocacao.alocar_chamada.return_value = expected_result

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=mock_alocacao,
    )
    cmd = AdquirirProximoPacienteCommand(organizacao_id=1, medico_id=medico_id)

    result = await service.adquirir_proximo_paciente(cmd)
    assert result == expected_result
    mock_alocacao.alocar_chamada.assert_called_once()


@pytest.mark.asyncio
async def test_adquirir_proximo_paciente_medico_ocupado_sem_retry() -> None:
    """Busy doctor raises MedicoOcupadoError immediately without retrying."""
    mock_valkey = AsyncMock()
    mock_session = AsyncMock()
    mock_alocacao = AsyncMock(spec=AlocacaoChamadaService)

    atend_id = uuid4()
    medico_id = uuid4()
    mock_valkey.zrange.return_value = [str(atend_id)]
    mock_alocacao.alocar_chamada.side_effect = MedicoOcupadoError(
        "Médico já possui chamada ativa."
    )

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=mock_alocacao,
    )
    cmd = AdquirirProximoPacienteCommand(
        organizacao_id=1,
        medico_id=medico_id,
        max_retries=3,
    )

    with pytest.raises(MedicoOcupadoError):
        await service.adquirir_proximo_paciente(cmd)

    # Must NOT retry when doctor is busy
    assert mock_alocacao.alocar_chamada.call_count == 1


@pytest.mark.asyncio
async def test_adquirir_proximo_paciente_retry_em_memoria() -> None:
    """In-memory retry catches code -1 and allocates 2nd patient seamlessly."""
    mock_valkey = AsyncMock()
    mock_session = AsyncMock()
    mock_alocacao = AsyncMock(spec=AlocacaoChamadaService)

    atend_1 = uuid4()
    atend_2 = uuid4()
    medico_id = uuid4()

    # 1st zrange returns atend_1, 2nd zrange returns atend_2
    mock_valkey.zrange.side_effect = [[str(atend_1)], [str(atend_2)]]

    expected_result = AlocacaoChamadaResult(
        atendimento_id=atend_2,
        medico_id=medico_id,
        status=StatusAtendimento.CHAMANDO_PACIENTE,
        chamada_iniciada_em=datetime.now(UTC),
        ttl_segundos=45,
    )

    # 1st call raises AtendimentoNaoDisponivelError, 2nd succeeds
    mock_alocacao.alocar_chamada.side_effect = [
        AtendimentoNaoDisponivelError("Paciente capturado concorrentemente."),
        expected_result,
    ]

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=mock_alocacao,
    )
    cmd = AdquirirProximoPacienteCommand(
        organizacao_id=1,
        medico_id=medico_id,
        max_retries=3,
    )

    result = await service.adquirir_proximo_paciente(cmd)
    assert result == expected_result
    assert mock_alocacao.alocar_chamada.call_count == 2


@pytest.mark.asyncio
async def test_adquirir_proximo_paciente_retry_esgotado_levanta_excecao() -> None:
    """Exhausting all retries raises AtendimentoNaoDisponivelError."""
    mock_valkey = AsyncMock()
    mock_session = AsyncMock()
    mock_alocacao = AsyncMock(spec=AlocacaoChamadaService)

    mock_valkey.zrange.return_value = [str(uuid4())]
    mock_alocacao.alocar_chamada.side_effect = AtendimentoNaoDisponivelError(
        "Paciente indisponível."
    )

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=mock_alocacao,
    )
    cmd = AdquirirProximoPacienteCommand(
        organizacao_id=1,
        medico_id=uuid4(),
        max_retries=3,
    )

    with pytest.raises(AtendimentoNaoDisponivelError) as exc_info:
        await service.adquirir_proximo_paciente(cmd)

    assert "após 3 tentativas" in str(exc_info.value)
    assert mock_alocacao.alocar_chamada.call_count == 3


@pytest.mark.asyncio
async def test_remover_e_obter_posicao_e_tamanho() -> None:
    """Test helper queue query and removal methods."""
    mock_valkey = AsyncMock()
    mock_session = AsyncMock()
    mock_valkey.zrem.return_value = 1
    mock_valkey.zrank.return_value = 4  # 0-indexed rank 4 -> position 5
    mock_valkey.zcard.return_value = 12
    mock_valkey.zrange.return_value = [b"id-1", b"id-2"]

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=AsyncMock(),
    )
    atend_id = uuid4()

    assert await service.remover_da_fila(1, atend_id) is True
    assert await service.obter_posicao_fila(1, atend_id) == 5
    assert await service.obter_tamanho_fila(1) == 12

    # When attendance is not in queue, rank is None -> returns None
    mock_valkey.zrank.return_value = None
    assert await service.obter_posicao_fila(1, atend_id) is None

    lista = await service.listar_fila(1, offset=0, limit=2)
    assert lista == ["id-1", "id-2"]


@pytest.mark.asyncio
async def test_atender_chamada_success_transitions_state_and_locks() -> None:
    """Transition from CHAMANDO_PACIENTE to EM_ATENDIMENTO with lock promotion."""
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock()
    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.pipeline.return_value.__aenter__.return_value = mock_pipe
    mock_session = AsyncMock()

    paciente_id = uuid7()
    medico_id = uuid7()
    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=paciente_id,
        tcle_hash="a" * 64,
    )
    atendimento.promover_para_apto()
    atendimento.iniciar_chamada(medico_id=medico_id)
    assert atendimento.status == StatusAtendimento.CHAMANDO_PACIENTE.value

    mock_session.get.return_value = atendimento

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=AsyncMock(),
    )

    await service.atender_chamada(atendimento.id)

    mock_session.get.assert_awaited_once_with(
        Atendimento, atendimento.id, with_for_update=True
    )
    assert atendimento.status == StatusAtendimento.EM_ATENDIMENTO.value
    mock_session.commit.assert_awaited_once()

    k_medico_ring = f"lock:1:medico:{medico_id}"
    k_atend_ring = f"lock:1:atendimento:{atendimento.id}"
    k_medico_consulta = f"lock:1:consulta_ativa:medico:{medico_id}"

    mock_pipe.delete.assert_any_call(k_medico_ring)
    mock_pipe.delete.assert_any_call(k_atend_ring)
    mock_pipe.set.assert_called_once_with(
        k_medico_consulta, str(atendimento.id), ex=7200
    )
    mock_pipe.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_atender_chamada_idempotent_when_already_em_atendimento() -> None:
    """Refreshes active consultation lock without error when already active."""
    mock_valkey = AsyncMock()
    mock_session = AsyncMock()

    paciente_id = uuid7()
    medico_id = uuid7()
    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=paciente_id,
        tcle_hash="a" * 64,
    )
    atendimento.promover_para_apto()
    atendimento.iniciar_chamada(medico_id=medico_id)
    atendimento.atender_chamada()
    assert atendimento.status == StatusAtendimento.EM_ATENDIMENTO.value

    mock_session.get.return_value = atendimento

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=AsyncMock(),
    )

    # Re-call should be idempotent
    await service.atender_chamada(atendimento.id)

    mock_session.get.assert_awaited_once_with(
        Atendimento, atendimento.id, with_for_update=True
    )
    mock_session.commit.assert_not_called()
    k_medico_consulta = f"lock:1:consulta_ativa:medico:{medico_id}"
    mock_valkey.set.assert_awaited_once_with(
        k_medico_consulta, str(atendimento.id), ex=7200
    )


@pytest.mark.asyncio
async def test_atender_chamada_invalid_status_raises_conflict() -> None:
    """Cannot directly answer attendance in APTO_PARA_CHAMADA."""
    mock_valkey = AsyncMock()
    mock_session = AsyncMock()

    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=uuid7(),
        tcle_hash="a" * 64,
    )
    atendimento.promover_para_apto()
    assert atendimento.status == StatusAtendimento.APTO_PARA_CHAMADA.value

    mock_session.get.return_value = atendimento

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=AsyncMock(),
    )

    with pytest.raises(TransicaoEstadoInvalidaError, match="Apenas atendimentos em"):
        await service.atender_chamada(atendimento.id)

    mock_session.get.assert_awaited_once_with(
        Atendimento, atendimento.id, with_for_update=True
    )


@pytest.mark.asyncio
async def test_atender_chamada_not_found_raises_404() -> None:
    """Non-existent attendance raises NotFoundError."""
    mock_valkey = AsyncMock()
    mock_session = AsyncMock()
    mock_session.get.return_value = None

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=AsyncMock(),
    )

    target_id = uuid4()
    with pytest.raises(NotFoundError, match="não encontrado"):
        await service.atender_chamada(target_id)

    mock_session.get.assert_awaited_once_with(
        Atendimento, target_id, with_for_update=True
    )


@pytest.mark.asyncio
async def test_resolver_ring_timeout_with_for_update_no_show() -> None:
    """Validate with_for_update=True and no-show transition when CHAMANDO_PACIENTE."""
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock()
    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.pipeline.return_value.__aenter__.return_value = mock_pipe
    mock_session = AsyncMock()

    paciente_id = uuid7()
    medico_id = uuid7()
    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=paciente_id,
        tcle_hash="a" * 64,
    )
    atendimento.promover_para_apto()
    atendimento.iniciar_chamada(medico_id=medico_id)
    assert atendimento.status == StatusAtendimento.CHAMANDO_PACIENTE.value

    mock_session.get.return_value = atendimento

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=AsyncMock(),
    )

    res = await service.resolver_ring_timeout(
        organizacao_id=1,
        atendimento_id=atendimento.id,
        medico_id=medico_id,
    )

    assert res == "no_show_recorded"
    mock_session.get.assert_awaited_once_with(
        Atendimento, atendimento.id, with_for_update=True
    )
    assert atendimento.status == StatusAtendimento.PACIENTE_AUSENTE.value
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolver_ring_timeout_with_for_update_active_consultation() -> None:
    """Validate with_for_update=True and active lock promotion when EM_ATENDIMENTO."""
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock()
    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.pipeline.return_value.__aenter__.return_value = mock_pipe
    mock_session = AsyncMock()

    paciente_id = uuid7()
    medico_id = uuid7()
    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=paciente_id,
        tcle_hash="a" * 64,
    )
    atendimento.promover_para_apto()
    atendimento.iniciar_chamada(medico_id=medico_id)
    atendimento.atender_chamada()
    assert atendimento.status == StatusAtendimento.EM_ATENDIMENTO.value

    mock_session.get.return_value = atendimento

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=AsyncMock(),
    )

    res = await service.resolver_ring_timeout(
        organizacao_id=1,
        atendimento_id=atendimento.id,
        medico_id=medico_id,
    )

    assert res == "active_consultation_preserved"
    mock_session.get.assert_awaited_once_with(
        Atendimento, atendimento.id, with_for_update=True
    )


@pytest.mark.asyncio
async def test_resolver_ring_timeout_with_for_update_not_found() -> None:
    """Validate with_for_update=True when attendance not found."""
    mock_valkey = MagicMock(spec=Redis)
    mock_session = AsyncMock()
    mock_session.get.return_value = None

    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=AsyncMock(),
    )

    target_id = uuid4()
    res = await service.resolver_ring_timeout(
        organizacao_id=1,
        atendimento_id=target_id,
        medico_id=uuid4(),
    )

    assert res == "not_found"
    mock_session.get.assert_awaited_once_with(
        Atendimento, target_id, with_for_update=True
    )
