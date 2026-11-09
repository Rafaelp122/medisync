"""Unit tests for asynchronous eligibility background task (RF-02, RN03)."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from src.modules.ambulatory import (
    ResultadoElegibilidade,
    StatusElegibilidade,
)
from src.modules.queue.domain.models import Atendimento, PrioridadeClinica
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.worker.tasks.eligibility import validar_elegibilidade_task

from tests.doubles import (
    FakeAsyncSession,
    FakeElegibilidadeNotifier,
    FakeEligibilityProvider,
    FakeValkey,
)


class FakeSessionFactory:
    """In-memory sessionmaker double yielding FakeAsyncSession."""

    def __init__(self, session: FakeAsyncSession) -> None:
        self.session = session

    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[FakeAsyncSession, None]:
        yield self.session


def _create_test_context(
    session: FakeAsyncSession, valkey: FakeValkey
) -> dict[str, Any]:
    return {
        "db_session_factory": FakeSessionFactory(session),
        "valkey_client": valkey,
    }


@pytest.mark.asyncio
async def test_validar_elegibilidade_sus_promotes_attendance_and_enqueues_valkey() -> (
    None
):
    """Under SUS, attendance is promoted to APTO_PARA_CHAMADA and ingested in ZSET."""
    org_id = 1
    atend_id = uuid4()
    paciente_id = uuid4()
    now = datetime.now(UTC)

    atendimento = Atendimento(
        id=atend_id,
        organizacao_id=org_id,
        paciente_id=paciente_id,
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="a" * 64,
        data_entrada_fila=now,
        criado_em=now,
    )

    session = FakeAsyncSession(entities={atend_id: atendimento})
    valkey = FakeValkey()
    ctx = _create_test_context(session, valkey)

    result = await validar_elegibilidade_task(
        ctx,
        organizacao_id=org_id,
        atendimento_id=str(atend_id),
        paciente_id=str(paciente_id),
    )

    assert result["status"] == "aprovado"
    assert result["aprovado"] is True
    assert result["codigo_autorizacao"] == "SUS-ISENTO"
    assert atendimento.status == StatusAtendimento.APTO_PARA_CHAMADA.value
    assert session.commits == 1
    score = await valkey.zscore(f"fila:{org_id}:aptos", str(atend_id))
    assert score == result["score"]


@pytest.mark.asyncio
async def test_validar_elegibilidade_falha_preserves_status_and_notifies() -> None:
    """When SUS verification fails, status is preserved and notifier is alerted
    (RF-05).
    """
    org_id = 1
    atend_id = uuid4()
    paciente_id = uuid4()
    now = datetime.now(UTC)

    atendimento = Atendimento(
        id=atend_id,
        organizacao_id=org_id,
        paciente_id=paciente_id,
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="a" * 64,
        data_entrada_fila=now,
        criado_em=now,
    )

    session = FakeAsyncSession(entities={atend_id: atendimento})
    valkey = FakeValkey()
    provider = FakeEligibilityProvider(
        ResultadoElegibilidade(
            aprovado=False,
            status=StatusElegibilidade.REJEITADO,
            motivo="Cadastro SUS irregular",
        )
    )
    notifier = FakeElegibilidadeNotifier()
    ctx = _create_test_context(session, valkey)

    result = await validar_elegibilidade_task(
        ctx,
        organizacao_id=org_id,
        atendimento_id=str(atend_id),
        paciente_id=str(paciente_id),
        provider=provider,
        notifier=notifier,
    )

    assert result["status"] == "REJEITADO"
    assert result["aprovado"] is False
    assert result["motivo"] == "Cadastro SUS irregular"
    assert atendimento.status == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
    assert session.commits == 0
    assert len(notifier.eventos_falha) == 1
    assert await valkey.zscore(f"fila:{org_id}:aptos", str(atend_id)) is None


@pytest.mark.asyncio
async def test_validar_elegibilidade_timeout_preserves_status() -> None:
    """When timeout occurs (15s), attendance is preserved without promotion."""
    org_id = 1
    atend_id = uuid4()
    paciente_id = uuid4()
    now = datetime.now(UTC)

    atendimento = Atendimento(
        id=atend_id,
        organizacao_id=org_id,
        paciente_id=paciente_id,
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="a" * 64,
        data_entrada_fila=now,
        criado_em=now,
    )

    session = FakeAsyncSession(entities={atend_id: atendimento})
    valkey = FakeValkey()
    provider = FakeEligibilityProvider(
        ResultadoElegibilidade(
            aprovado=False,
            status=StatusElegibilidade.TIMEOUT,
            motivo="Tempo limite de 15s excedido",
        )
    )
    notifier = FakeElegibilidadeNotifier()
    ctx = _create_test_context(session, valkey)

    result = await validar_elegibilidade_task(
        ctx,
        organizacao_id=org_id,
        atendimento_id=str(atend_id),
        paciente_id=str(paciente_id),
        provider=provider,
        notifier=notifier,
    )

    assert result["status"] == "TIMEOUT"
    assert result["aprovado"] is False
    assert atendimento.status == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
    assert session.commits == 0
    assert len(notifier.eventos_falha) == 1
    assert await valkey.zscore(f"fila:{org_id}:aptos", str(atend_id)) is None


@pytest.mark.asyncio
async def test_validar_elegibilidade_already_promoted() -> None:
    """If attendance was already promoted to APTO_PARA_CHAMADA, skip promotion."""
    org_id = 1
    atend_id = uuid4()
    paciente_id = uuid4()
    now = datetime.now(UTC)

    atendimento = Atendimento(
        id=atend_id,
        organizacao_id=org_id,
        paciente_id=paciente_id,
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="a" * 64,
        data_entrada_fila=now,
        criado_em=now,
    )

    session = FakeAsyncSession(entities={atend_id: atendimento})
    valkey = FakeValkey()
    ctx = _create_test_context(session, valkey)

    result = await validar_elegibilidade_task(
        ctx,
        organizacao_id=org_id,
        atendimento_id=str(atend_id),
        paciente_id=str(paciente_id),
    )

    assert result["status"] == "already_promoted"
    assert result["aprovado"] is True
    assert session.commits == 0


@pytest.mark.asyncio
async def test_validar_elegibilidade_not_found_returns_safe_status() -> None:
    """If attendance is not found in database, returns safe not_found response."""
    org_id = 1
    atend_id = uuid4()
    paciente_id = uuid4()

    session = FakeAsyncSession()
    valkey = FakeValkey()
    ctx = _create_test_context(session, valkey)

    result = await validar_elegibilidade_task(
        ctx,
        organizacao_id=org_id,
        atendimento_id=str(atend_id),
        paciente_id=str(paciente_id),
    )

    assert result["status"] == "not_found"
    assert result["aprovado"] is True
    assert session.commits == 0
