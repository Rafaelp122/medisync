"""Unit tests for attendance eligibility regularization in queue (US-05 / NC-QUE-04).

Regras: RN01 (Score Imutável de Antiguidade), RN03 (Preservação de Antiguidade).
Especificação: docs/user-stories/US-05-regularizacao-elegibilidade-fila.md
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from src.core.errors import NotFoundError, ValidationError
from src.modules.queue.application.dtos import (
    RegularizacaoFilaCommand,
)
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.exceptions import TransicaoEstadoInvalidaError
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)
from src.modules.queue.domain.scoring import calcular_score

from tests.doubles import FakeAsyncSession, FakeValkey


@pytest.mark.asyncio
async def test_regularizar_contingencia_sucesso_restaura_score_original_no_valkey() -> (
    None
):
    """Paciente regularizado restaura score original com antiguidade justa (RN01, RN03).

    Regras: RN01 (Score Imutável), RN03 (Preservação de Antiguidade), NC-QUE-04.
    História: docs/user-stories/US-05-regularizacao-elegibilidade-fila.md
    """
    now = datetime.now(UTC)
    t0 = now - timedelta(minutes=30)
    t1 = now - timedelta(minutes=5)
    org_id = 1

    # Paciente 1 admitido há 30 min (T0), prioridade URGENTE, retido em elegibilidade
    paciente_1 = Atendimento(
        id=uuid4(),
        organizacao_id=org_id,
        paciente_id=uuid4(),
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="a" * 64,
        criado_em=t0,
        data_entrada_fila=t0,
    )

    # Paciente 2 admitido há 5 min (T1), prioridade URGENTE, já ativo na fila de aptos
    paciente_2 = Atendimento(
        id=uuid4(),
        organizacao_id=org_id,
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        criado_em=t1,
        data_entrada_fila=t1,
    )

    fake_valkey = FakeValkey()
    score_p2 = calcular_score(paciente_2.prioridade_clinica, t1)
    await fake_valkey.zadd(f"fila:{org_id}:aptos", {str(paciente_2.id): score_p2})

    fake_session = FakeAsyncSession(
        entities={paciente_1.id: paciente_1, paciente_2.id: paciente_2}
    )

    fila_service = FilaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("Any", fake_session),
        alocacao_service=MagicMock(spec=AlocacaoChamadaService),
    )

    cmd = RegularizacaoFilaCommand(
        organizacao_id=org_id,
        atendimento_id=paciente_1.id,
        tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
        motivo="Indisponibilidade gateway operadora",
    )

    result = await fila_service.regularizar_atendimento(cmd)

    assert result.promovido is True
    assert result.status == StatusAtendimento.APTO_PARA_CHAMADA.value

    score_p1 = await fake_valkey.zscore(f"fila:{org_id}:aptos", str(paciente_1.id))
    score_p2_valkey = await fake_valkey.zscore(
        f"fila:{org_id}:aptos", str(paciente_2.id)
    )
    assert score_p1 is not None
    assert score_p2_valkey is not None
    # Score de Paciente 1 (T0) deve ser menor que o de Paciente 2 (T1) (FIFO justo)
    assert score_p1 < score_p2_valkey

    # Paciente 1 assume a primeira posição na fila (FIFO justo RN01)
    rank_p1 = await fake_valkey.zrank(f"fila:{org_id}:aptos", str(paciente_1.id))
    assert rank_p1 == 0


@pytest.mark.asyncio
async def test_regularizar_idempotencia_duplo_acionamento() -> None:
    """Segunda regularização para atendimento já apto é idempotente (sem mutação).

    Regras: RN03 (Idempotência de Regularização), NC-QUE-04.
    História: docs/user-stories/US-05-regularizacao-elegibilidade-fila.md
    """
    now = datetime.now(UTC)
    t0 = now - timedelta(minutes=20)
    org_id = 1

    paciente = Atendimento(
        id=uuid4(),
        organizacao_id=org_id,
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        criado_em=t0,
        data_entrada_fila=t0,
    )

    fake_valkey = FakeValkey()
    score_original = calcular_score(paciente.prioridade_clinica, t0)
    await fake_valkey.zadd(f"fila:{org_id}:aptos", {str(paciente.id): score_original})

    fake_session = FakeAsyncSession(entities={paciente.id: paciente})

    fila_service = FilaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("Any", fake_session),
        alocacao_service=MagicMock(spec=AlocacaoChamadaService),
    )

    cmd = RegularizacaoFilaCommand(
        organizacao_id=org_id,
        atendimento_id=paciente.id,
        tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
        motivo="Segunda regularização redundante",
    )

    result = await fila_service.regularizar_atendimento(cmd)

    assert result.promovido is False
    assert result.status == "already_promoted"

    score_atual = await fake_valkey.zscore(f"fila:{org_id}:aptos", str(paciente.id))
    assert score_atual == score_original


@pytest.mark.asyncio
async def test_regularizar_atendimento_inexistente_ou_tenant_divergente() -> None:
    """Tentativa de regularizar atendimento inexistente ou de outro tenant lança erro.

    Regras: Isolamento Multi-tenant (ADR-001), Tratamento de Erros Ricos.
    História: docs/user-stories/US-05-regularizacao-elegibilidade-fila.md
    """
    fake_valkey = FakeValkey()
    fake_session = FakeAsyncSession()
    fila_service = FilaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("Any", fake_session),
        alocacao_service=MagicMock(spec=AlocacaoChamadaService),
    )

    # 1. Atendimento inexistente
    inexistente_id = uuid4()
    cmd_inexistente = RegularizacaoFilaCommand(
        organizacao_id=1,
        atendimento_id=inexistente_id,
        tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
        motivo="Tentativa de regularizar atendimento inexistente",
    )
    with pytest.raises(NotFoundError) as exc_inexistente:
        await fila_service.regularizar_atendimento(cmd_inexistente)

    assert str(inexistente_id) in str(exc_inexistente.value)
    assert "1" in str(exc_inexistente.value)

    # 2. Tenant divergente (pertence ao tenant 99, comando pede tenant 1)
    paciente_outro_tenant = Atendimento(
        id=uuid4(),
        organizacao_id=99,
        paciente_id=uuid4(),
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
    )
    fake_session_tenant = FakeAsyncSession(
        entities={paciente_outro_tenant.id: paciente_outro_tenant}
    )
    fila_service_tenant = FilaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("Any", fake_session_tenant),
        alocacao_service=MagicMock(spec=AlocacaoChamadaService),
    )
    cmd_divergente = RegularizacaoFilaCommand(
        organizacao_id=1,
        atendimento_id=paciente_outro_tenant.id,
        tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
        motivo="Tentativa cross-tenant indevida",
    )
    with pytest.raises(NotFoundError) as exc_divergente:
        await fila_service_tenant.regularizar_atendimento(cmd_divergente)

    assert str(paciente_outro_tenant.id) in str(exc_divergente.value)
    assert "1" in str(exc_divergente.value)


@pytest.mark.asyncio
async def test_regularizar_status_invalido_rejeita_com_offending_value() -> None:
    """Status incompatível é rejeitado com mensagem contendo o valor ofensivo.

    Regras: Transição Válida de Estados Clínicos, Clean Code para Agentes de IA.
    História: docs/user-stories/US-05-regularizacao-elegibilidade-fila.md
    """
    paciente_em_atendimento = Atendimento(
        id=uuid4(),
        organizacao_id=1,
        paciente_id=uuid4(),
        status=StatusAtendimento.EM_ATENDIMENTO,
        prioridade_clinica=PrioridadeClinica.URGENTE,
    )

    fake_valkey = FakeValkey()
    fake_session = FakeAsyncSession(
        entities={paciente_em_atendimento.id: paciente_em_atendimento}
    )
    fila_service = FilaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("Any", fake_session),
        alocacao_service=MagicMock(spec=AlocacaoChamadaService),
    )

    cmd = RegularizacaoFilaCommand(
        organizacao_id=1,
        atendimento_id=paciente_em_atendimento.id,
        tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
        motivo="Tentativa de regularizar atendimento já em consulta médica",
    )

    with pytest.raises(TransicaoEstadoInvalidaError) as exc_info:
        await fila_service.regularizar_atendimento(cmd)

    assert StatusAtendimento.EM_ATENDIMENTO.value in str(exc_info.value)


@pytest.mark.asyncio
async def test_regularizar_motivo_vazio_lanca_validation_error() -> None:
    """Motivo vazio ou apenas espaços em branco rejeita com ValidationError.

    Regras: Validação Estrita de Dados de Entrada, Rastreabilidade de Auditoria.
    História: docs/user-stories/US-05-regularizacao-elegibilidade-fila.md
    """
    paciente = Atendimento(
        id=uuid4(),
        organizacao_id=1,
        paciente_id=uuid4(),
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
    )

    fake_valkey = FakeValkey()
    fake_session = FakeAsyncSession(entities={paciente.id: paciente})
    fila_service = FilaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("Any", fake_session),
        alocacao_service=MagicMock(spec=AlocacaoChamadaService),
    )

    for motivo_invalido in ["", "   ", "\t  \n"]:
        with pytest.raises(ValidationError):
            cmd = RegularizacaoFilaCommand(
                organizacao_id=1,
                atendimento_id=paciente.id,
                tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
                motivo=motivo_invalido,
            )
            await fila_service.regularizar_atendimento(cmd)


@pytest.mark.asyncio
async def test_regularizar_reenvio_convenio_enfileira_tarefa_assincrona() -> None:
    """Reenvio de convênio enfileira nova tarefa ARQ e mantém status aguardando.

    Regras: US-05, RF-02, RF-05.
    História: docs/user-stories/US-05-regularizacao-elegibilidade-fila.md
    """
    paciente = Atendimento(
        id=uuid4(),
        organizacao_id=1,
        paciente_id=uuid4(),
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="a" * 64,
    )

    fake_valkey = FakeValkey()
    fake_session = FakeAsyncSession(entities={paciente.id: paciente})
    mock_arq_pool = MagicMock()
    mock_arq_pool.enqueue_job = AsyncMock()

    fila_service = FilaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("Any", fake_session),
        alocacao_service=MagicMock(spec=AlocacaoChamadaService),
        arq_pool=mock_arq_pool,
    )

    cmd = RegularizacaoFilaCommand(
        organizacao_id=1,
        atendimento_id=paciente.id,
        tipo_contingencia="CONVENIO_REAPRESENTADO",
        motivo="Carteirinha corrigida pelo paciente",
        operadora_id="BRADESCO-SAUDE",
        numero_carteirinha="987654321",
    )

    result = await fila_service.regularizar_atendimento(cmd)

    assert result.promovido is False
    assert result.status == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
    mock_arq_pool.enqueue_job.assert_awaited_once()
    assert (
        mock_arq_pool.enqueue_job.call_args.kwargs["operadora_id"] == "BRADESCO-SAUDE"
    )
