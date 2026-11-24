"""Unit tests for FilaService admission and unified intake/triage seam (Fase 4)."""

from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from arq.connections import ArqRedis
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import ValidationError
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    AdmissaoAtendimentoResult,
)
from src.modules.queue.application.ports.shift_policy_reader_port import ShiftPolicyDTO
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.exceptions import AdmissaoFilaSuspensaError
from src.modules.triage.application.services.triage_service import TriageService
from src.modules.triage.domain.exceptions import EmergenciaCriticaSamuError

from tests.doubles import (
    FakeArqPool,
    FakeAsyncSession,
    FakeEmergencyNotifier,
    FakeQueueEngine,
    FakeShiftPolicyReader,
)


@pytest.fixture
def fake_engine() -> FakeQueueEngine:
    return FakeQueueEngine(medicos_ativos={uuid4(), uuid4()})


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


@pytest.fixture
def emergency_notifier() -> FakeEmergencyNotifier:
    return FakeEmergencyNotifier()


@pytest.fixture
def fake_arq_pool() -> FakeArqPool:
    return FakeArqPool()


@pytest.fixture
def triage_service(
    fake_session: FakeAsyncSession,
    emergency_notifier: FakeEmergencyNotifier,
) -> TriageService:
    return TriageService(
        session=cast("AsyncSession", fake_session),
        emergency_notifier=emergency_notifier,
    )


@pytest.fixture
def fila_service(
    fake_engine: FakeQueueEngine,
    fake_session: FakeAsyncSession,
    triage_service: TriageService,
    fake_arq_pool: FakeArqPool,
) -> FilaService:
    return FilaService(
        queue_engine=fake_engine,
        db_session=cast("AsyncSession", fake_session),
        triage_port=triage_service,
        shift_policy_reader=FakeShiftPolicyReader(),
        arq_pool=cast("ArqRedis", fake_arq_pool),
    )


@pytest.mark.asyncio
async def test_admitir_paciente_success(
    fila_service: FilaService,
    fake_session: FakeAsyncSession,
    fake_arq_pool: FakeArqPool,
    fake_engine: FakeQueueEngine,
) -> None:
    pac_id = uuid4()
    cmd = AdmissaoAtendimentoCommand(
        paciente_id=pac_id,
        queixa_principal="Dor de garganta e febre baixa há 2 dias",
        sintomas=["febre"],
        escala_dor=4,
        tcle_texto="Termo de consentimento livre e esclarecido para telemedicina",
    )

    result = await fila_service.admitir_paciente(cmd)
    assert isinstance(result, AdmissaoAtendimentoResult)
    assert result.paciente_id == pac_id
    assert result.status_atendimento == "APTO_PARA_CHAMADA"
    assert result.prioridade_clinica in (3, 4)
    assert result.alerta_samu_disparado is False
    assert result.tcle_hash is not None
    assert len(result.tcle_hash) == 64
    assert len(fake_session.added) == 2
    assert fake_session.commits == 1
    assert result.atendimento_id in fake_engine.fila_scores
    assert fake_engine.cota_diaria_usada == 1
    assert len(fake_arq_pool.enqueued_jobs) == 0


@pytest.mark.asyncio
async def test_admitir_paciente_emergencia_critica_raises(
    fila_service: FilaService,
    emergency_notifier: FakeEmergencyNotifier,
    fake_engine: FakeQueueEngine,
) -> None:
    cmd = AdmissaoAtendimentoCommand(
        paciente_id=uuid4(),
        queixa_principal="Paciente inconsciente sem respirar",
        sintomas=["inconsciencia"],
        escala_dor=10,
        tcle_hash="a" * 64,
    )

    with pytest.raises(EmergenciaCriticaSamuError):
        await fila_service.admitir_paciente(cmd)

    assert len(emergency_notifier.sent_alerts) == 1
    assert "inconsciencia" in emergency_notifier.sent_alerts[0].sintomas_alerta
    assert fake_engine.cota_diaria_usada == 0
    assert len(fake_engine.fila_scores) == 0


@pytest.mark.asyncio
async def test_admitir_paciente_sus_direto_vai_para_apto_e_zset_sem_worker(
    fila_service: FilaService,
    fake_engine: FakeQueueEngine,
    fake_arq_pool: FakeArqPool,
) -> None:
    pac_id = uuid4()
    cmd = AdmissaoAtendimentoCommand(
        paciente_id=pac_id,
        queixa_principal="Febre e tosse",
        sintomas=["tosse"],
        escala_dor=2,
        tcle_texto="Termo concordado",
        cpf="12345678901",
        cns="123456789012345",
    )

    result = await fila_service.admitir_paciente(cmd)
    assert result.status_atendimento == "APTO_PARA_CHAMADA"
    assert result.atendimento_id in fake_engine.fila_scores
    assert len(fake_arq_pool.enqueued_jobs) == 0


@pytest.mark.asyncio
async def test_admitir_paciente_sem_medicos_ativos_suspende(
    fake_session: FakeAsyncSession,
    triage_service: TriageService,
) -> None:
    engine_vazio = FakeQueueEngine(medicos_ativos=set())
    service = FilaService(
        queue_engine=engine_vazio,
        db_session=cast("AsyncSession", fake_session),
        triage_port=triage_service,
        shift_policy_reader=FakeShiftPolicyReader(),
    )
    cmd = AdmissaoAtendimentoCommand(
        paciente_id=uuid4(),
        queixa_principal="Cefaleia leve",
        sintomas=[],
        escala_dor=2,
        tcle_hash="b" * 64,
    )

    with pytest.raises(AdmissaoFilaSuspensaError) as exc_info:
        await service.admitir_paciente(cmd)

    assert exc_info.value.motivo == "SEM_MEDICOS_ATIVOS"
    assert fake_session.commits == 0


@pytest.mark.asyncio
async def test_admitir_paciente_usa_parametros_shift_policy_reader(
    fake_session: FakeAsyncSession,
    triage_service: TriageService,
) -> None:
    """ShiftPolicyReaderPort parameters control backpressure even without overrides."""
    engine = FakeQueueEngine(medicos_ativos={uuid4()})
    for _ in range(5):
        engine.fila_scores[uuid4()] = 3000

    strict_policy = FakeShiftPolicyReader(
        ShiftPolicyDTO(
            alpha_backpressure=1.5,
            cota_diaria_maxima=300,
            tma_padrao_segundos=1200,
        )
    )
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", fake_session),
        triage_port=triage_service,
        shift_policy_reader=strict_policy,
    )
    # Load = 5 * 1200 * 1.5 / 1 = 9000s > 3600s -> suspended!
    cmd = AdmissaoAtendimentoCommand(
        paciente_id=uuid4(),
        queixa_principal="Cefaleia leve",
        sintomas=[],
        escala_dor=2,
        tcle_hash="b" * 64,
        tempo_restante_segundos=3600.0,
    )

    with pytest.raises(AdmissaoFilaSuspensaError) as exc_info:
        await service.admitir_paciente(cmd)

    assert exc_info.value.motivo == "CAPACIDADE_EXCEDIDA"
    assert engine.cota_diaria_usada == 0


@pytest.mark.asyncio
async def test_admitir_paciente_tcle_ausente_raises(
    fila_service: FilaService,
) -> None:
    cmd = AdmissaoAtendimentoCommand(
        paciente_id=uuid4(),
        queixa_principal="Cefaleia leve",
        sintomas=[],
        escala_dor=2,
        tcle_texto="",
        tcle_hash=None,
    )

    with pytest.raises(ValidationError):
        await fila_service.admitir_paciente(cmd)


@pytest.mark.asyncio
async def test_fila_service_admitir_paciente_sem_triage_port_raises(
    fake_engine: FakeQueueEngine,
    fake_session: FakeAsyncSession,
) -> None:
    """Verifica erro de runtime caso TriagePort não tenha sido injetada."""
    service_sem_triage = FilaService(
        queue_engine=fake_engine,
        db_session=cast("AsyncSession", fake_session),
        triage_port=None,
    )
    cmd = AdmissaoAtendimentoCommand(
        paciente_id=uuid4(),
        queixa_principal="Cefaleia",
        sintomas=[],
        tcle_texto="TCLE",
    )
    with pytest.raises(RuntimeError, match="TriagePort não configurado"):
        await service_sem_triage.admitir_paciente(cmd)
