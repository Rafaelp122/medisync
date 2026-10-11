"""Unit tests for daily admission quota (RN05 / NC-QUE-01) in Valkey."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
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
from src.modules.triage.infrastructure.adapters.samu_emergency_notifier_adapter import (
    SamuEmergencyNotifierAdapter,
)


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_fila_service(
    mock_db_session: AsyncMock,
    mock_controle_admissao: MagicMock,
    triage_service: TriageService,
) -> FilaService:
    valkey = AsyncMock()
    valkey.zcard = AsyncMock(return_value=1)
    alocacao = MagicMock()
    return FilaService(
        valkey=valkey,
        db_session=mock_db_session,
        alocacao_service=alocacao,
        controle_admissao=mock_controle_admissao,
        triage_port=triage_service,
    )


@pytest.fixture
def mock_controle_admissao() -> MagicMock:
    controle = MagicMock(spec=ControleAdmissaoService)
    controle.obter_admissoes_hoje = AsyncMock(return_value=10)
    controle.incrementar_admissoes_hoje = AsyncMock(return_value=11)
    controle.avaliar_admissao = AsyncMock(
        return_value=AvaliacaoAdmissaoResult(
            admissao_permitida=True,
            motivo_bloqueio=None,
            carga_estimada_segundos=600.0,
            tempo_restante_segundos=14400.0,
            pacientes_aguardando=1,
            medicos_ativos=2,
            alpha_utilizado=1.25,
            mensagem_explicativa="Admissão permitida.",
        )
    )
    return controle


@pytest.fixture
def triage_service(mock_db_session: AsyncMock) -> TriageService:
    return TriageService(
        session=mock_db_session,
        emergency_notifier=SamuEmergencyNotifierAdapter(),
    )


@pytest.mark.asyncio
async def test_admissao_consulta_e_incrementa_cota_diaria(
    mock_db_session: AsyncMock,
    mock_fila_service: MagicMock,
    mock_controle_admissao: MagicMock,
    triage_service: TriageService,
) -> None:
    service = AdmissaoAtendimentoService(
        session=mock_db_session,
        fila_service=mock_fila_service,
        controle_admissao=mock_controle_admissao,
        triage_port=triage_service,
    )

    cmd = AdmissaoAtendimentoCommand(
        organizacao_id=42,
        paciente_id=uuid4(),
        queixa_principal="Febre baixa há 1 dia",
        sintomas=["febre"],
        tcle_texto="Consentimento para teleconsulta",
        cota_diaria_maxima=300,
    )

    result = await service.admitir_paciente(cmd)
    assert result.organizacao_id == 42

    # Verifica que consultou a cota do Valkey
    mock_controle_admissao.obter_admissoes_hoje.assert_awaited_once_with(42)

    # Verifica que avaliou admissão passando total de admissões do dia
    avaliacao_call = mock_controle_admissao.avaliar_admissao.call_args[0][0]
    assert avaliacao_call.total_admissoes_hoje == 10
    assert avaliacao_call.cota_diaria_maxima == 300

    # Verifica que incrementou a cota no Valkey após persistência
    mock_controle_admissao.incrementar_admissoes_hoje.assert_awaited_once_with(42)


@pytest.mark.asyncio
async def test_admissao_bloqueada_quando_cota_diaria_atingida(
    mock_db_session: AsyncMock,
    mock_fila_service: MagicMock,
    mock_controle_admissao: MagicMock,
    triage_service: TriageService,
) -> None:
    mock_controle_admissao.obter_admissoes_hoje = AsyncMock(return_value=300)
    mock_controle_admissao.avaliar_admissao = AsyncMock(
        return_value=AvaliacaoAdmissaoResult(
            admissao_permitida=False,
            motivo_bloqueio="COTA_ATINGIDA",
            carga_estimada_segundos=0.0,
            tempo_restante_segundos=14400.0,
            pacientes_aguardando=1,
            medicos_ativos=2,
            alpha_utilizado=1.25,
            mensagem_explicativa=(
                "A cota diária de atendimentos da unidade foi atingida."
            ),
        )
    )

    service = AdmissaoAtendimentoService(
        session=mock_db_session,
        fila_service=mock_fila_service,
        controle_admissao=mock_controle_admissao,
        triage_port=triage_service,
    )

    cmd = AdmissaoAtendimentoCommand(
        organizacao_id=42,
        paciente_id=uuid4(),
        queixa_principal="Cansaço leve",
        sintomas=[],
        tcle_texto="Consentimento para teleconsulta",
        cota_diaria_maxima=300,
    )

    with pytest.raises(AdmissaoFilaSuspensaError) as exc_info:
        await service.admitir_paciente(cmd)

    assert exc_info.value.motivo == "COTA_ATINGIDA"
    mock_controle_admissao.incrementar_admissoes_hoje.assert_not_called()
    mock_db_session.commit.assert_not_called()
