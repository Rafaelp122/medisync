"""Unit tests for AdmissaoAtendimentoService and unified intake/triage seam (Fase 4)."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from src.core.errors import ValidationError
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    AdmissaoAtendimentoResult,
    AvaliacaoAdmissaoResult,
)
from src.modules.queue.application.services.admissao_service import (
    AdmissaoAtendimentoService,
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
def mock_fila_service() -> MagicMock:
    fila = MagicMock(spec=FilaService)
    fila.obter_tamanho_fila = AsyncMock(return_value=2)
    return fila


@pytest.fixture
def mock_controle_admissao() -> MagicMock:
    controle = MagicMock(spec=ControleAdmissaoService)
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
def admissao_service(
    mock_db_session: AsyncMock,
    mock_fila_service: MagicMock,
    mock_controle_admissao: MagicMock,
    triage_service: TriageService,
    mock_arq_pool: AsyncMock,
) -> AdmissaoAtendimentoService:
    return AdmissaoAtendimentoService(
        session=mock_db_session,
        fila_service=mock_fila_service,
        controle_admissao=mock_controle_admissao,
        triage_port=triage_service,
        arq_pool=mock_arq_pool,
    )


@pytest.mark.asyncio
async def test_admitir_paciente_success(
    admissao_service: AdmissaoAtendimentoService,
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

    result = await admissao_service.admitir_paciente(cmd)
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
    admissao_service: AdmissaoAtendimentoService,
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
        await admissao_service.admitir_paciente(cmd)

    assert len(mock_emergency_notifier.sent_alerts) == 1
    assert mock_emergency_notifier.sent_alerts[0].organizacao_id == 1
    assert "inconsciencia" in mock_emergency_notifier.sent_alerts[0].sintomas_alerta


@pytest.mark.asyncio
async def test_admitir_paciente_enqueues_validar_elegibilidade_task(
    admissao_service: AdmissaoAtendimentoService,
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

    result = await admissao_service.admitir_paciente(cmd)
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
    admissao_service: AdmissaoAtendimentoService,
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
        await admissao_service.admitir_paciente(cmd)


@pytest.mark.asyncio
async def test_admitir_paciente_tcle_ausente_raises(
    admissao_service: AdmissaoAtendimentoService,
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
        await admissao_service.admitir_paciente(cmd)
