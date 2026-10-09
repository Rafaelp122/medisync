"""Unit tests for FilaService QueueStorePort implementations (Fase 3)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.errors import NotFoundError
from src.modules.queue.application.ports.queue_store_port import (
    AdmissaoAptoResult,
    AtendimentoSnapshotDTO,
    QueueStorePort,
)
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.controle_admissao_service import (
    ControleAdmissaoService,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import (
    PrioridadeClinica,
    StatusAtendimento,
)


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_valkey() -> MagicMock:
    valkey = MagicMock(spec=Redis)
    valkey.zadd = AsyncMock(return_value=1)
    valkey.zscore = AsyncMock(return_value=None)
    valkey.exists = AsyncMock(return_value=0)
    valkey.get = AsyncMock(return_value=None)
    pipe = MagicMock()
    pipe.delete = MagicMock()
    pipe.set = MagicMock()
    pipe.execute = AsyncMock()
    valkey.pipeline.return_value.__aenter__.return_value = pipe
    return valkey


@pytest.fixture
def fila_service(mock_valkey: MagicMock, mock_session: AsyncMock) -> FilaService:
    alocacao_mock = MagicMock(spec=AlocacaoChamadaService)
    admissao_mock = MagicMock(spec=ControleAdmissaoService)
    return FilaService(
        valkey=mock_valkey,
        db_session=mock_session,
        alocacao_service=alocacao_mock,
        controle_admissao=admissao_mock,
    )


def test_fila_service_satisfies_queue_store_port(fila_service: FilaService) -> None:
    assert isinstance(fila_service, QueueStorePort)


@pytest.mark.asyncio
async def test_admitir_atendimento_apto_success(
    fila_service: FilaService, mock_session: AsyncMock, mock_valkey: MagicMock
) -> None:
    atend_id = uuid4()
    org_id = 1
    mock_atend = MagicMock(spec=Atendimento)
    mock_atend.id = atend_id
    mock_atend.organizacao_id = org_id
    mock_atend.status = StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
    mock_atend.prioridade_clinica = PrioridadeClinica.URGENTE
    mock_atend.data_entrada_fila = datetime.now(UTC)
    mock_atend.criado_em = datetime.now(UTC)
    mock_session.get.return_value = mock_atend

    res = await fila_service.admitir_atendimento_apto(org_id, atend_id)
    assert isinstance(res, AdmissaoAptoResult)
    assert res.promovido is True
    assert res.status == "aprovado"
    mock_atend.promover_para_apto.assert_called_once()
    mock_session.commit.assert_awaited_once()
    mock_valkey.zadd.assert_awaited_once()


@pytest.mark.asyncio
async def test_admitir_atendimento_apto_not_found(
    fila_service: FilaService, mock_session: AsyncMock
) -> None:
    mock_session.get.return_value = None
    with pytest.raises(NotFoundError):
        await fila_service.admitir_atendimento_apto(1, uuid4())


@pytest.mark.asyncio
async def test_resolver_ring_timeout_no_show(
    fila_service: FilaService, mock_session: AsyncMock, mock_valkey: MagicMock
) -> None:
    atend_id = uuid4()
    med_id = uuid4()
    org_id = 1
    mock_atend = MagicMock(spec=Atendimento)
    mock_atend.id = atend_id
    mock_atend.organizacao_id = org_id
    mock_atend.paciente_id = uuid4()
    mock_atend.status = StatusAtendimento.CHAMANDO_PACIENTE.value
    mock_session.get.return_value = mock_atend

    action = await fila_service.resolver_ring_timeout(org_id, atend_id, med_id)
    assert action == "no_show_recorded"
    mock_atend.registrar_ausencia_paciente.assert_called_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_concluir_atendimento_success(
    fila_service: FilaService, mock_session: AsyncMock
) -> None:
    atend_id = uuid4()
    mock_atend = MagicMock(spec=Atendimento)
    mock_atend.id = atend_id
    mock_atend.status = StatusAtendimento.EM_ATENDIMENTO.value
    mock_session.get.return_value = mock_atend

    await fila_service.concluir_atendimento(atend_id)
    mock_atend.concluir_atendimento.assert_called_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_buscar_atendimento(
    fila_service: FilaService, mock_session: AsyncMock
) -> None:
    atend_id = uuid4()
    org_id = 1
    pac_id = uuid4()
    now = datetime.now(UTC)

    mock_atend = MagicMock(spec=Atendimento)
    mock_atend.id = atend_id
    mock_atend.organizacao_id = org_id
    mock_atend.paciente_id = pac_id
    mock_atend.medico_id = None
    mock_atend.status = StatusAtendimento.CONCLUIDO.value
    mock_atend.prioridade_clinica = PrioridadeClinica.POUCO_URGENTE
    mock_atend.tcle_hash = "a" * 64
    mock_atend.data_entrada_fila = now
    mock_atend.criado_em = now

    mock_exec_res = MagicMock()
    mock_exec_res.scalar_one_or_none.return_value = mock_atend
    mock_session.execute.return_value = mock_exec_res

    snapshot = await fila_service.buscar_atendimento(atend_id)
    assert isinstance(snapshot, AtendimentoSnapshotDTO)
    assert snapshot.id == atend_id
    assert snapshot.status == StatusAtendimento.CONCLUIDO.value
    assert snapshot.is_terminal is True
