"""Unit tests for FilaService operations (position, cancel, deterioration)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from src.core.errors import NotFoundError
from src.modules.queue.application.dtos import (
    PioraClinicaCommand,
)
from src.modules.queue.application.ports.triage_port import TriagePort
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.controle_admissao_service import (
    ControleAdmissaoService,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento


@dataclass
class FakeTriageEvaluation:
    prioridade_clinica: int
    tcle_hash: str = "a" * 64
    alerta_samu_disparado: bool = False
    instrucao_redirecionamento: str | None = None


@pytest.fixture
def mock_valkey() -> AsyncMock:
    valkey = AsyncMock(spec=Redis)
    valkey.zcard = AsyncMock(return_value=5)
    valkey.zrank = AsyncMock(return_value=2)  # 0-indexed rank 2 -> position 3
    valkey.zrem = AsyncMock(return_value=1)
    valkey.zadd = AsyncMock(return_value=1)
    valkey.delete = AsyncMock(return_value=1)
    valkey.pipeline = MagicMock()
    return valkey


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock()
    session.get = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_alocacao_service() -> MagicMock:
    return MagicMock(spec=AlocacaoChamadaService)


@pytest.fixture
def mock_controle_admissao() -> MagicMock:
    ctrl = MagicMock(spec=ControleAdmissaoService)
    ctrl.obter_medicos_ativos_count = AsyncMock(return_value=2)
    return ctrl


@pytest.fixture
def mock_triage_port() -> MagicMock:
    port = MagicMock(spec=TriagePort)
    return port


@pytest.fixture
def fila_service(
    mock_valkey: AsyncMock,
    mock_db_session: AsyncMock,
    mock_alocacao_service: MagicMock,
    mock_controle_admissao: MagicMock,
    mock_triage_port: MagicMock,
) -> FilaService:
    return FilaService(
        valkey=mock_valkey,
        db_session=mock_db_session,
        alocacao_service=mock_alocacao_service,
        controle_admissao=mock_controle_admissao,
        triage_port=mock_triage_port,
    )


@pytest.mark.asyncio
async def test_obter_posicao_e_estimativa_em_fila(
    fila_service: FilaService,
    mock_db_session: AsyncMock,
) -> None:
    atend_id = uuid4()
    atend = Atendimento(
        id=atend_id,
        organizacao_id=10,
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=3,
        tcle_hash="a" * 64,
        data_entrada_fila=datetime.now(UTC),
    )
    mock_db_session.get.return_value = atend

    res = await fila_service.obter_posicao_e_estimativa(
        organizacao_id=10, atendimento_id=atend_id
    )

    assert res.atendimento_id == atend_id
    assert res.status == StatusAtendimento.APTO_PARA_CHAMADA.value
    assert res.posicao == 3
    assert res.total_aguardando == 5
    # (posicao 3 * 600 TMA) / 2 medicos = 900s
    assert res.tempo_estimado_segundos == 900


@pytest.mark.asyncio
async def test_obter_posicao_e_estimativa_atendimento_nao_encontrado(
    fila_service: FilaService,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.get.return_value = None

    with pytest.raises(NotFoundError):
        await fila_service.obter_posicao_e_estimativa(
            organizacao_id=10, atendimento_id=uuid4()
        )


@pytest.mark.asyncio
async def test_cancelar_atendimento_paciente_sucesso(
    fila_service: FilaService,
    mock_db_session: AsyncMock,
    mock_valkey: AsyncMock,
) -> None:
    atend_id = uuid4()
    atend = Atendimento(
        id=atend_id,
        organizacao_id=10,
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=3,
        tcle_hash="a" * 64,
        data_entrada_fila=datetime.now(UTC),
    )
    mock_db_session.get.return_value = atend

    res = await fila_service.cancelar_atendimento_paciente(
        organizacao_id=10,
        atendimento_id=atend_id,
        motivo="Melhora dos sintomas",
    )

    assert res.atendimento_id == atend_id
    assert res.status == StatusAtendimento.CANCELADO_PACIENTE.value
    assert atend.status == StatusAtendimento.CANCELADO_PACIENTE.value
    mock_valkey.zrem.assert_awaited_once_with("fila:10:aptos", str(atend_id))
    mock_db_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_processar_piora_clinica_desvio_samu(
    fila_service: FilaService,
    mock_db_session: AsyncMock,
    mock_triage_port: MagicMock,
    mock_valkey: AsyncMock,
) -> None:
    atend_id = uuid4()
    atend = Atendimento(
        id=atend_id,
        organizacao_id=10,
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=4,
        tcle_hash="a" * 64,
        data_entrada_fila=datetime.now(UTC),
    )
    mock_db_session.get.return_value = atend

    # Simula avaliação de risco Nível 1 SAMU
    mock_triage_port.avaliar_risco = AsyncMock(
        return_value=FakeTriageEvaluation(
            prioridade_clinica=1,
            alerta_samu_disparado=True,
            instrucao_redirecionamento="Ligue 192 imediatamente ou procure emergência.",
            tcle_hash="a" * 64,
        )
    )

    cmd = PioraClinicaCommand(
        organizacao_id=10,
        atendimento_id=atend_id,
        novos_sintomas=["dor_toracica", "falta_de_ar"],
        escala_dor=9,
        queixa_adicional="Dor intensa irradiando para o braço",
    )

    res = await fila_service.processar_piora_clinica(cmd)

    assert res.atendimento_id == atend_id
    assert res.prioridade_clinica == 1
    assert res.alerta_samu_disparado is True
    assert res.redirecionado_emergencia is True
    assert res.nova_posicao is None
    # Verifica que foi removido da fila virtual
    mock_valkey.zrem.assert_awaited_once_with("fila:10:aptos", str(atend_id))
    assert atend.status == StatusAtendimento.CANCELADO_PACIENTE.value
    mock_db_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_processar_piora_clinica_reclassificacao_prioridade(
    fila_service: FilaService,
    mock_db_session: AsyncMock,
    mock_triage_port: MagicMock,
    mock_valkey: AsyncMock,
) -> None:
    atend_id = uuid4()
    atend = Atendimento(
        id=atend_id,
        organizacao_id=10,
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=4,  # Pouco Urgente (Verde)
        tcle_hash="a" * 64,
        data_entrada_fila=datetime.now(UTC),
    )
    mock_db_session.get.return_value = atend

    # Simula reclassificação para Nível 2 (Muito Urgente - Laranja)
    mock_triage_port.avaliar_risco = AsyncMock(
        return_value=FakeTriageEvaluation(
            prioridade_clinica=2,
            alerta_samu_disparado=False,
            instrucao_redirecionamento=None,
            tcle_hash="a" * 64,
        )
    )

    cmd = PioraClinicaCommand(
        organizacao_id=10,
        atendimento_id=atend_id,
        novos_sintomas=["febre_alta"],
        escala_dor=7,
    )

    res = await fila_service.processar_piora_clinica(cmd)

    assert res.atendimento_id == atend_id
    assert res.prioridade_clinica == 2
    assert res.alerta_samu_disparado is False
    assert res.redirecionado_emergencia is False
    assert atend.prioridade_clinica == 2
    # Recalcula e atualiza ZSET com novo score mais prioritário
    mock_valkey.zadd.assert_awaited_once()
    mock_db_session.commit.assert_awaited_once()
