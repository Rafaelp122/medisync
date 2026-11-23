"""Unit tests for stochastic admission control and backpressure (RN05)."""

import logging
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import ValidationError
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    AvaliarAdmissaoCommand,
)
from src.modules.queue.application.ports.shift_policy_reader_port import ShiftPolicyDTO
from src.modules.queue.application.services.controle_admissao_service import (
    ControleAdmissaoService,
    avaliar_capacidade_admissao,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.exceptions import AdmissaoFilaSuspensaError
from src.modules.triage.application.dtos import TriageRiskEvaluationDTO

from tests.doubles import (
    FakeAsyncSession,
    FakeQueueEngine,
    FakeShiftPolicyReader,
    FakeTriagePort,
)


def test_avaliar_capacidade_admissao_permitida() -> None:
    """Admission is allowed when workload is well within remaining shift time."""
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
    res_120 = avaliar_capacidade_admissao(
        pacientes_aguardando=5,
        medicos_ativos=1,
        tempo_restante_segundos=3700,
        tma_estimado_segundos=600,
        alpha=1.20,
    )
    assert res_120.admissao_permitida is True

    res_130 = avaliar_capacidade_admissao(
        pacientes_aguardando=5,
        medicos_ativos=1,
        tempo_restante_segundos=3700,
        tma_estimado_segundos=600,
        alpha=1.30,
    )
    assert res_130.admissao_permitida is False


@pytest.mark.asyncio
async def test_controle_admissao_service_loga_transbordo_quando_bloqueada(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Logs structured overflow warning when shift capacity is exceeded."""
    engine = FakeQueueEngine()
    service = ControleAdmissaoService(queue_engine=engine)

    cmd = AvaliarAdmissaoCommand(
        medicos_ativos=1,
        tempo_restante_segundos=1000,
        pacientes_aguardando=10,
        tma_estimado_segundos=600,
        alpha_margem=1.25,
    )

    with caplog.at_level(logging.WARNING):
        res = await service.avaliar_admissao(cmd)

    assert res.admissao_permitida is False
    assert res.motivo_bloqueio == "CAPACIDADE_EXCEDIDA"
    assert "CAPACIDADE_EXCEDIDA" in caplog.text
    assert "7500.0s" in caplog.text


@pytest.mark.asyncio
async def test_controle_admissao_service_admissao_permitida_dinamica() -> None:
    """Queries FakeQueueEngine ZSET size when pacientes_aguardando is omitted."""
    engine = FakeQueueEngine()
    engine.fila_scores[uuid4()] = 1000
    engine.fila_scores[uuid4()] = 2000
    service = ControleAdmissaoService(queue_engine=engine)

    cmd = AvaliarAdmissaoCommand(
        medicos_ativos=5,
        tempo_restante_segundos=10000,
        pacientes_aguardando=2,
    )
    res = await service.avaliar_admissao(cmd)
    assert res.admissao_permitida is True
    assert res.pacientes_aguardando == 2

    cmd_none = AvaliarAdmissaoCommand(
        medicos_ativos=5,
        tempo_restante_segundos=10000,
        pacientes_aguardando=None,
    )
    res_none = await service.avaliar_admissao(cmd_none)
    assert res_none.admissao_permitida is True
    assert res_none.pacientes_aguardando == 2


@pytest.mark.asyncio
async def test_controle_admissao_service_medicos_ativos() -> None:
    """Test active doctor presence synchronization via QueueEnginePort."""
    engine = FakeQueueEngine()
    service = ControleAdmissaoService(queue_engine=engine)
    doc_id = uuid4()

    await service.registrar_medico_ativo(doc_id)
    assert doc_id in engine.medicos_ativos
    assert await service.obter_medicos_ativos_count() == 1

    await service.desregistrar_medico_ativo(doc_id)
    assert doc_id not in engine.medicos_ativos
    assert await service.obter_medicos_ativos_count() == 0


@pytest.mark.asyncio
async def test_fila_service_admitir_paciente_backpressure_e_estorno_cota() -> None:
    """admitir_paciente blocks on capacity, rolls back quota, and preserves ZSET."""
    doc_id = uuid4()
    engine = FakeQueueEngine(medicos_ativos={doc_id}, cota_diaria_usada=5)
    for idx in range(10):
        engine.fila_scores[uuid4()] = 3000 + idx

    session = FakeAsyncSession()
    triage = FakeTriagePort(
        evaluation=TriageRiskEvaluationDTO(prioridade_clinica=3, tcle_hash="a" * 64)
    )
    policy_reader = FakeShiftPolicyReader(
        ShiftPolicyDTO(
            alpha_backpressure=1.25,
            cota_diaria_maxima=300,
            tma_padrao_segundos=600,
        )
    )
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        triage_port=triage,
        shift_policy_reader=policy_reader,
    )

    # 1. Blocked: 10 waiting * 600 * 1.25 / 1 doctor = 7500s > 1000s
    blocked_cmd = AdmissaoAtendimentoCommand(
        paciente_id=uuid4(),
        queixa_principal="Febre moderada",
        sintomas=["febre"],
        tcle_hash="a" * 64,
        tempo_restante_segundos=1000,
    )
    with pytest.raises(AdmissaoFilaSuspensaError) as exc_info:
        await service.admitir_paciente(blocked_cmd)

    assert exc_info.value.status_code == 503
    assert exc_info.value.motivo == "CAPACIDADE_EXCEDIDA"
    assert engine.cota_diaria_usada == 5
    assert len(engine.fila_scores) == 10
    assert session.commits == 0

    # 2. Allowed: add 9 more doctors (total 10) -> load 750s <= 10000s
    for _ in range(9):
        await engine.registrar_medico_ativo(uuid4())

    allowed_cmd = AdmissaoAtendimentoCommand(
        paciente_id=uuid4(),
        queixa_principal="Febre moderada",
        sintomas=["febre"],
        tcle_hash="a" * 64,
        tempo_restante_segundos=10000,
    )
    result = await service.admitir_paciente(allowed_cmd)
    assert result.atendimento_id in engine.fila_scores
    assert len(engine.fila_scores) == 11
    assert engine.cota_diaria_usada == 6
    assert session.commits == 1
