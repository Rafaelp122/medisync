"""Unit tests for FilaService admission and unified intake/triage seam (Fase 4)."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from src.core.errors import ValidationError
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    AdmissaoAtendimentoResult,
    AvaliacaoAdmissaoResult,
)
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.controle_admissao_service import (
    ControleAdmissaoService,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.exceptions import AdmissaoFilaSuspensaError
from src.modules.triage.application.services.triage_service import TriageService
from src.modules.triage.domain.exceptions import EmergenciaCriticaSamuError
from src.modules.triage.infrastructure.adapters.samu_emergency_notifier_adapter import (
    SamuEmergencyNotifierAdapter,
)


@pytest.fixture
def mock_valkey() -> AsyncMock:
    valkey = AsyncMock(spec=Redis)
    valkey.zcard = AsyncMock(return_value=2)
    return valkey


@pytest.fixture
def mock_alocacao_service() -> MagicMock:
    return MagicMock(spec=AlocacaoChamadaService)


@pytest.fixture
def mock_controle_admissao() -> MagicMock:
    controle = MagicMock(spec=ControleAdmissaoService)
    controle.obter_admissoes_hoje = AsyncMock(return_value=0)
    controle.incrementar_admissoes_hoje = AsyncMock(return_value=1)
    controle.avaliar_admissao = AsyncMock(
        return_value=AvaliacaoAdmissaoResult(
            admissao_permitida=True,
            motivo_bloqueio=None,
            carga_estimada_segundos=1800.0,
            tempo_restante_segundos=14400.0,
            pacientes_aguardando=2,
            medicos_ativos=2,
            alpha_utilizado=1.25,
            mensagem_explicativa="Admissão autorizada.",
        )
    )
    return controle


@pytest.fixture
def mock_emergency_notifier() -> SamuEmergencyNotifierAdapter:
    return SamuEmergencyNotifierAdapter()


@pytest.fixture
def mock_arq_pool() -> AsyncMock:
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock(return_value=MagicMock(job_id="test_job_123"))
    return pool


@pytest.fixture
def triage_service(
    mock_db_session: AsyncMock,
    mock_emergency_notifier: SamuEmergencyNotifierAdapter,
) -> TriageService:
    return TriageService(
        session=mock_db_session,
        emergency_notifier=mock_emergency_notifier,
    )


@pytest.fixture
def fila_service(
    mock_valkey: AsyncMock,
    mock_db_session: AsyncMock,
    mock_alocacao_service: MagicMock,
    mock_controle_admissao: MagicMock,
    triage_service: TriageService,
    mock_arq_pool: AsyncMock,
) -> FilaService:
    return FilaService(
        valkey=mock_valkey,
        db_session=mock_db_session,
        alocacao_service=mock_alocacao_service,
        controle_admissao=mock_controle_admissao,
        triage_port=triage_service,
        arq_pool=mock_arq_pool,
    )


@pytest.mark.asyncio
async def test_admitir_paciente_success(
    fila_service: FilaService,
    mock_db_session: AsyncMock,
    mock_arq_pool: AsyncMock,
) -> None:
    pac_id = uuid4()
    cmd = AdmissaoAtendimentoCommand(
        organizacao_id=1,
        paciente_id=pac_id,
        queixa_principal="Dor de garganta e febre baixa há 2 dias",
        sintomas=["febre"],
        escala_dor=4,
        tcle_texto="Termo de consentimento livre e esclarecido para telemedicina",
    )

    result = await fila_service.admitir_paciente(cmd)
    assert isinstance(result, AdmissaoAtendimentoResult)
    assert result.organizacao_id == 1
    assert result.paciente_id == pac_id
    assert result.prioridade_clinica in (3, 4)
    assert result.alerta_samu_disparado is False
    assert mock_db_session.add.call_count == 2
    mock_db_session.commit.assert_awaited_once()
    mock_arq_pool.enqueue_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_admitir_paciente_emergencia_critica_raises(
    fila_service: FilaService,
    mock_emergency_notifier: SamuEmergencyNotifierAdapter,
) -> None:
    cmd = AdmissaoAtendimentoCommand(
        organizacao_id=1,
        paciente_id=uuid4(),
        queixa_principal="Paciente inconsciente sem respirar",
        sintomas=["inconsciencia"],
        escala_dor=10,
        tcle_hash="a" * 64,
    )

    with pytest.raises(EmergenciaCriticaSamuError):
        await fila_service.admitir_paciente(cmd)

    assert len(mock_emergency_notifier.sent_alerts) == 1
    assert mock_emergency_notifier.sent_alerts[0].organizacao_id == 1
    assert "inconsciencia" in mock_emergency_notifier.sent_alerts[0].sintomas_alerta


@pytest.mark.asyncio
async def test_admitir_paciente_enqueues_validar_elegibilidade_task(
    fila_service: FilaService,
    mock_arq_pool: AsyncMock,
) -> None:
    pac_id = uuid4()
    cmd = AdmissaoAtendimentoCommand(
        organizacao_id=1,
        paciente_id=pac_id,
        queixa_principal="Febre e tosse",
        sintomas=["tosse"],
        escala_dor=2,
        tcle_texto="Termo concordado",
        cpf="12345678901",
        cns="123456789012345",
        operadora_id="UNIMED",
        numero_carteirinha="998877",
    )

    result = await fila_service.admitir_paciente(cmd)
    mock_arq_pool.enqueue_job.assert_awaited_once_with(
        "validar_elegibilidade_task",
        organizacao_id=1,
        atendimento_id=str(result.atendimento_id),
        paciente_id=str(pac_id),
        cpf="12345678901",
        cns="123456789012345",
        operadora_id="UNIMED",
        numero_carteirinha="998877",
        _job_id=f"elegibilidade:{result.atendimento_id}",
    )


@pytest.mark.asyncio
async def test_admitir_paciente_backpressure_suspensa(
    fila_service: FilaService,
    mock_controle_admissao: MagicMock,
) -> None:
    mock_controle_admissao.avaliar_admissao.return_value = AvaliacaoAdmissaoResult(
        admissao_permitida=False,
        motivo_bloqueio="TEMPO_INSUFICIENTE",
        carga_estimada_segundos=15000.0,
        tempo_restante_segundos=1000.0,
        pacientes_aguardando=20,
        medicos_ativos=1,
        alpha_utilizado=1.25,
        mensagem_explicativa="Capacidade máxima de atendimento excedida.",
    )

    cmd = AdmissaoAtendimentoCommand(
        organizacao_id=1,
        paciente_id=uuid4(),
        queixa_principal="Cefaleia leve",
        sintomas=[],
        escala_dor=2,
        tcle_hash="b" * 64,
    )

    with pytest.raises(AdmissaoFilaSuspensaError):
        await fila_service.admitir_paciente(cmd)


@pytest.mark.asyncio
async def test_admitir_paciente_tcle_ausente_raises(
    fila_service: FilaService,
) -> None:
    cmd = AdmissaoAtendimentoCommand(
        organizacao_id=1,
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
async def test_fila_service_admitir_paciente_direct_success(
    fila_service: FilaService,
    mock_db_session: AsyncMock,
    mock_arq_pool: AsyncMock,
    mock_controle_admissao: MagicMock,
) -> None:
    """Verifica admissão executada diretamente pelo FilaService (Fase 2)."""
    pac_id = uuid4()
    cmd = AdmissaoAtendimentoCommand(
        organizacao_id=1,
        paciente_id=pac_id,
        queixa_principal="Febre e tosse seca",
        sintomas=["febre", "tosse"],
        escala_dor=3,
        tcle_texto="Termo de consentimento aceito",
    )

    result = await fila_service.admitir_paciente(cmd)
    assert isinstance(result, AdmissaoAtendimentoResult)
    assert result.organizacao_id == 1
    assert result.paciente_id == pac_id
    assert result.prioridade_clinica in (3, 4)
    assert result.alerta_samu_disparado is False
    assert mock_db_session.add.call_count == 2
    mock_db_session.commit.assert_awaited_once()
    mock_controle_admissao.incrementar_admissoes_hoje.assert_awaited_once_with(1)
    mock_arq_pool.enqueue_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_fila_service_admitir_paciente_organizacao_invalida_raises(
    fila_service: FilaService,
) -> None:
    """Valida rejeição de organizacao_id menor ou igual a zero."""
    cmd = AdmissaoAtendimentoCommand(
        organizacao_id=0,
        paciente_id=uuid4(),
        queixa_principal="Cefaleia",
        sintomas=[],
        tcle_texto="TCLE",
    )
    with pytest.raises(ValidationError, match="organizacao_id deve ser positivo"):
        await fila_service.admitir_paciente(cmd)


@pytest.mark.asyncio
async def test_fila_service_admitir_paciente_sem_triage_port_raises(
    mock_valkey: AsyncMock,
    mock_db_session: AsyncMock,
    mock_alocacao_service: MagicMock,
) -> None:
    """Verifica erro de runtime caso TriagePort não tenha sido injetada."""
    service_sem_triage = FilaService(
        valkey=mock_valkey,
        db_session=mock_db_session,
        alocacao_service=mock_alocacao_service,
        triage_port=None,
    )
    cmd = AdmissaoAtendimentoCommand(
        organizacao_id=1,
        paciente_id=uuid4(),
        queixa_principal="Cefaleia",
        sintomas=[],
        tcle_texto="TCLE",
    )
    with pytest.raises(RuntimeError, match="TriagePort não configurado"):
        await service_sem_triage.admitir_paciente(cmd)
