"""Unit tests for stochastic admission control and backpressure (RN05)."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from src.core.errors import ValidationError
from src.modules.queue.application.dtos import (
    AvaliarAdmissaoCommand,
    IngressarFilaComBackpressureCommand,
)
from src.modules.queue.application.ports.queue_overflow_notifier import (
    LoggingQueueOverflowNotifier,
    QueueOverflowEvent,
)
from src.modules.queue.application.services.controle_admissao_service import (
    ControleAdmissaoService,
    avaliar_capacidade_admissao,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.exceptions import AdmissaoFilaSuspensaError
from src.modules.queue.domain.models import PrioridadeClinica


class SpyQueueOverflowNotifier:
    """Spy notifier collecting emitted overflow events for assertions."""

    def __init__(self) -> None:
        self.events: list[QueueOverflowEvent] = []

    async def emitir_transbordo(self, event: QueueOverflowEvent) -> None:
        self.events.append(event)


def test_avaliar_capacidade_admissao_permitida() -> None:
    """Admission is allowed when workload is well within remaining shift time."""
    # Workload = (2 * 600 * 1.25) / 2 = 750s <= 3600s
    res = avaliar_capacidade_admissao(
        pacientes_aguardando=2,
        medicos_ativos=2,
        tempo_restante_segundos=3600,
        tma_estimado_segundos=600,
        alpha=1.25,
    )
    assert res.admissao_permitida is True
    assert res.motivo_bloqueio is None
    assert res.carga_estimada_segundos == 750.0


def test_avaliar_capacidade_admissao_capacidade_excedida() -> None:
    """Admission is suspended when workload exceeds remaining shift time."""
    # Workload = (10 * 600 * 1.25) / 1 = 7500s > 3600s
    res = avaliar_capacidade_admissao(
        pacientes_aguardando=10,
        medicos_ativos=1,
        tempo_restante_segundos=3600,
        tma_estimado_segundos=600,
        alpha=1.25,
    )
    assert res.admissao_permitida is False
    assert res.motivo_bloqueio == "CAPACIDADE_EXCEDIDA"
    assert res.carga_estimada_segundos == 7500.0
    assert "capacidade do plantão atual foi atingida" in res.mensagem_explicativa


def test_avaliar_capacidade_admissao_sem_medicos_ativos() -> None:
    """Admission is suspended immediately when no active doctors are on shift."""
    res = avaliar_capacidade_admissao(
        pacientes_aguardando=0,
        medicos_ativos=0,
        tempo_restante_segundos=3600,
    )
    assert res.admissao_permitida is False
    assert res.motivo_bloqueio == "SEM_MEDICOS_ATIVOS"
    assert "não há médicos plantonistas ativos" in res.mensagem_explicativa


def test_avaliar_capacidade_admissao_cota_diaria_atingida() -> None:
    """Admission is suspended when daily quota is reached (Condition A)."""
    res = avaliar_capacidade_admissao(
        pacientes_aguardando=0,
        medicos_ativos=5,
        tempo_restante_segundos=3600,
        total_admissoes_hoje=300,
        cota_diaria_maxima=300,
    )
    assert res.admissao_permitida is False
    assert res.motivo_bloqueio == "COTA_ATINGIDA"
    assert "cota diária de atendimentos da unidade" in res.mensagem_explicativa


def test_avaliar_capacidade_admissao_validacao_parametros() -> None:
    """Invalid alpha or TMA raises ValidationError."""
    with pytest.raises(ValidationError):
        avaliar_capacidade_admissao(
            pacientes_aguardando=1,
            medicos_ativos=1,
            tempo_restante_segundos=1000,
            alpha=0,
        )

    with pytest.raises(ValidationError):
        avaliar_capacidade_admissao(
            pacientes_aguardando=1,
            medicos_ativos=1,
            tempo_restante_segundos=1000,
            tma_estimado_segundos=-10,
        )


def test_alpha_range_sensibilidade() -> None:
    """Validate behavior across the regulatory alpha range [1.20, 1.30]."""
    # 5 patients, 1 doctor, TMA 600s, remaining time 3700s
    # With alpha=1.20: (5 * 600 * 1.20) / 1 = 3600s <= 3700s -> ALLOWED
    res_120 = avaliar_capacidade_admissao(
        pacientes_aguardando=5,
        medicos_ativos=1,
        tempo_restante_segundos=3700,
        tma_estimado_segundos=600,
        alpha=1.20,
    )
    assert res_120.admissao_permitida is True

    # With alpha=1.30: (5 * 600 * 1.30) / 1 = 3900s > 3700s -> BLOCKED
    res_130 = avaliar_capacidade_admissao(
        pacientes_aguardando=5,
        medicos_ativos=1,
        tempo_restante_segundos=3700,
        tma_estimado_segundos=600,
        alpha=1.30,
    )
    assert res_130.admissao_permitida is False


@pytest.mark.asyncio
async def test_controle_admissao_service_emissao_evento() -> None:
    """Emits QUEUE_OVERFLOW_TRANSIT event when capacity is breached."""
    mock_valkey = AsyncMock()
    spy_notifier = SpyQueueOverflowNotifier()
    service = ControleAdmissaoService(valkey=mock_valkey, notifier=spy_notifier)

    cmd = AvaliarAdmissaoCommand(
        organizacao_id=1,
        medicos_ativos=1,
        tempo_restante_segundos=1000,
        pacientes_aguardando=10,  # Load: 10 * 600 * 1.25 / 1 = 7500s > 1000s
        tma_estimado_segundos=600,
        alpha_margem=1.25,
    )

    res = await service.avaliar_admissao(cmd)
    assert res.admissao_permitida is False
    assert len(spy_notifier.events) == 1

    ev = spy_notifier.events[0]
    assert ev.evento == "QUEUE_OVERFLOW_TRANSIT"
    assert ev.organizacao_id == 1
    assert ev.motivo == "CAPACIDADE_EXCEDIDA"
    assert ev.pacientes_aguardando == 10
    assert ev.medicos_ativos == 1
    assert ev.carga_estimada_segundos == 7500.0
    assert ev.alpha_utilizado == 1.25


@pytest.mark.asyncio
async def test_controle_admissao_service_admissao_permitida_nao_emite_evento() -> None:
    """Does not emit overflow event when admission is permitted."""
    mock_valkey = AsyncMock()
    spy_notifier = SpyQueueOverflowNotifier()
    service = ControleAdmissaoService(valkey=mock_valkey, notifier=spy_notifier)

    mock_valkey.zcard.return_value = 2

    # Case 1: pacientes_aguardando explicitly passed
    cmd = AvaliarAdmissaoCommand(
        organizacao_id=1,
        medicos_ativos=5,
        tempo_restante_segundos=10000,
        pacientes_aguardando=2,
    )
    res = await service.avaliar_admissao(cmd)
    assert res.admissao_permitida is True
    assert len(spy_notifier.events) == 0

    # Case 2: pacientes_aguardando queried dynamically from Valkey ZSET
    cmd_none = AvaliarAdmissaoCommand(
        organizacao_id=1,
        medicos_ativos=5,
        tempo_restante_segundos=10000,
        pacientes_aguardando=None,
    )
    res_none = await service.avaliar_admissao(cmd_none)
    assert res_none.admissao_permitida is True
    mock_valkey.zcard.assert_called_once_with("fila:1:aptos")


@pytest.mark.asyncio
async def test_controle_admissao_service_medicos_ativos_e_cotas() -> None:
    """Test active doctor presence and daily admission counters in Valkey."""
    mock_valkey = AsyncMock()
    service = ControleAdmissaoService(valkey=mock_valkey)
    doc_id = uuid4()

    mock_valkey.scard.return_value = 4
    mock_valkey.incr.return_value = 42
    mock_valkey.get.return_value = b"42"

    await service.registrar_medico_ativo(1, doc_id)
    mock_valkey.sadd.assert_called_once_with("plantao:1:medicos_ativos", str(doc_id))

    await service.desregistrar_medico_ativo(1, doc_id)
    mock_valkey.srem.assert_called_once_with("plantao:1:medicos_ativos", str(doc_id))

    assert await service.obter_medicos_ativos_count(1) == 4
    assert await service.incrementar_admissoes_hoje(1) == 42
    assert await service.obter_admissoes_hoje(1) == 42


@pytest.mark.asyncio
async def test_logging_overflow_notifier_coverage() -> None:
    """Ensure default LoggingQueueOverflowNotifier executes cleanly."""
    notifier = LoggingQueueOverflowNotifier()
    ev = QueueOverflowEvent(
        organizacao_id=1,
        motivo="CAPACIDADE_EXCEDIDA",
        pacientes_aguardando=5,
        medicos_ativos=1,
        tempo_restante_segundos=1000,
        carga_estimada_segundos=3750,
        mensagem_orientacao="Aguarde",
    )
    # Must not raise
    await notifier.emitir_transbordo(ev)


@pytest.mark.asyncio
async def test_fila_service_admitir_com_backpressure() -> None:
    """Test admitir_com_backpressure with admission allowed and blocked."""
    mock_valkey = AsyncMock()
    mock_session = AsyncMock()
    mock_valkey.zcard.return_value = 10
    mock_valkey.zadd.return_value = 1
    mock_valkey.zrank.return_value = 0

    spy_notifier = SpyQueueOverflowNotifier()
    controle = ControleAdmissaoService(valkey=mock_valkey, notifier=spy_notifier)
    service = FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        controle_admissao=controle,
    )

    atend_id = uuid4()
    # 1. Blocked: 10 waiting patients, 1 doctor, 1000s remaining -> load 7500s > 1000s
    blocked_cmd = IngressarFilaComBackpressureCommand(
        organizacao_id=1,
        atendimento_id=atend_id,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        medicos_ativos=1,
        tempo_restante_segundos=1000,
    )
    with pytest.raises(AdmissaoFilaSuspensaError) as exc_info:
        await service.admitir_com_backpressure(blocked_cmd)

    assert exc_info.value.status_code == 503
    assert exc_info.value.motivo == "CAPACIDADE_EXCEDIDA"
    assert len(spy_notifier.events) == 1

    # 2. Allowed: 10 doctors, 10000s remaining -> load 750s <= 10000s
    allowed_cmd = IngressarFilaComBackpressureCommand(
        organizacao_id=1,
        atendimento_id=atend_id,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        medicos_ativos=10,
        tempo_restante_segundos=10000,
    )
    result = await service.admitir_com_backpressure(allowed_cmd)
    assert result.atendimento_id == atend_id
    assert result.posicao == 1
