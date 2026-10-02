"""Unit tests for queue ingestion service, 64-bit scoring, and retry loop (RN01)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from src.core.errors import ValidationError
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
    calcular_score_fila,
)
from src.modules.queue.domain.exceptions import (
    AtendimentoNaoDisponivelError,
    MedicoOcupadoError,
)
from src.modules.queue.domain.models import PrioridadeClinica, StatusAtendimento


def test_calcular_score_fila_formula() -> None:
    """Validate 64-bit score formula: (priority * 10^12) + timestamp."""
    epoch_fixed = 1_700_000_000
    score_p1 = calcular_score_fila(PrioridadeClinica.EMERGENCIA, epoch_fixed)
    assert score_p1 == 1_001_700_000_000

    score_p2 = calcular_score_fila(PrioridadeClinica.MUITO_URGENTE, epoch_fixed)
    assert score_p2 == 2_001_700_000_000

    score_p4 = calcular_score_fila(PrioridadeClinica.POUCO_URGENTE, epoch_fixed)
    assert score_p4 == 4_001_700_000_000

    score_p5 = calcular_score_fila(PrioridadeClinica.NAO_URGENTE, epoch_fixed)
    assert score_p5 == 5_001_700_000_000

    # With datetime instance
    dt = datetime.fromtimestamp(epoch_fixed, tz=UTC)
    assert calcular_score_fila(PrioridadeClinica.URGENTE, dt) == 3_001_700_000_000

    # With default timestamp (current time)
    score_default = calcular_score_fila(PrioridadeClinica.URGENTE)
    assert 3_000_000_000_000 < score_default < 4_000_000_000_000


def test_calcular_score_fila_invalid_priority() -> None:
    """Invalid priorities outside [1, 5] must raise ValidationError."""
    with pytest.raises(ValidationError):
        calcular_score_fila(0)

    with pytest.raises(ValidationError):
        calcular_score_fila(6)


def test_prevalencia_clinica_invariante_rn01() -> None:
    """Clinical urgency must mathematically precede lower urgency (RN01)."""
    now = datetime.now(UTC)
    ten_years_ago = now - timedelta(days=3650)

    # A level 2 patient who arrived right now
    score_lvl2_now = calcular_score_fila(PrioridadeClinica.MUITO_URGENTE, now)

    # A level 4 patient who waited for 10 years
    score_lvl4_old = calcular_score_fila(PrioridadeClinica.POUCO_URGENTE, ten_years_ago)

    # Level 2 must have a LOWER score than level 4 (ZSET sorts ascending)
    assert score_lvl2_now < score_lvl4_old


@pytest.mark.asyncio
async def test_ingressar_fila_unit() -> None:
    """Ingress attendance and verify Valkey ZADD and ZRANK invocation."""
    mock_valkey = AsyncMock()
    mock_session = AsyncMock()
    mock_valkey.zadd.return_value = 1
    mock_valkey.zrank.return_value = 0  # 0-indexed rank -> position 1

    service = FilaService(valkey=mock_valkey, db_session=mock_session)
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

    service = FilaService(valkey=mock_valkey, db_session=mock_session)
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

    service = FilaService(valkey=mock_valkey, db_session=mock_session)
    atend_id = uuid4()

    assert await service.remover_da_fila(1, atend_id) is True
    assert await service.obter_posicao_fila(1, atend_id) == 5
    assert await service.obter_tamanho_fila(1) == 12

    # When attendance is not in queue, rank is None -> returns None
    mock_valkey.zrank.return_value = None
    assert await service.obter_posicao_fila(1, atend_id) is None

    lista = await service.listar_fila(1, offset=0, limit=2)
    assert lista == ["id-1", "id-2"]
