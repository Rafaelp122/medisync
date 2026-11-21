"""Integration tests for asynchronous health insurance and SUS eligibility flow
(RF-02, RN03).
"""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from src.core.database import async_session_factory
from src.core.valkey import close_valkey_pool, get_valkey_client
from src.modules.ambulatory import (
    EligibilityProviderPort,
    ResultadoElegibilidade,
    StatusElegibilidade,
)
from src.modules.queue.domain.models import Atendimento, PrioridadeClinica
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.worker.settings import startup
from src.worker.tasks.eligibility import validar_elegibilidade_task

from tests.factories.identity import make_configuracao_unidade, make_paciente
from tests.factories.queue import make_atendimento

_VALID_TCLE_HASH = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"


@pytest.fixture(autouse=True)
async def clean_database_and_valkey() -> AsyncGenerator[None, None]:
    """Ensure clean PostgreSQL tables and Valkey keys for each test."""
    from tests.helpers import clean_database_and_valkey as _clean

    await _clean()
    yield
    await _clean()


@pytest.mark.asyncio
async def test_end_to_end_sus_eligibility_flow() -> None:
    """Public SUS instance validates instantly, promotes to APTO and ingests in ZSET."""
    unidade = make_configuracao_unidade(modo_publico_sus=True)
    patient = make_paciente()
    atend = make_atendimento(
        paciente_id=patient.id,
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value,
        prioridade_clinica=PrioridadeClinica.MUITO_URGENTE,
        tcle_hash=_VALID_TCLE_HASH,
    )

    async with async_session_factory() as session:
        session.add_all([unidade, patient, atend])
        await session.commit()

    ctx: dict[str, Any] = {}
    await startup(ctx)
    try:
        result = await validar_elegibilidade_task(
            ctx,
            atendimento_id=str(atend.id),
            paciente_id=str(patient.id),
        )

        assert result["status"] == "aprovado"
        assert result["aprovado"] is True
        assert result["codigo_autorizacao"] == "SUS-ISENTO"

        # Verify PostgreSQL state promotion
        async with async_session_factory() as session:
            refreshed = await session.get(Atendimento, atend.id)
            assert refreshed is not None
            assert refreshed.status == StatusAtendimento.APTO_PARA_CHAMADA.value

        # Verify Valkey queue ingestion
        k_fila = "fila:aptos"
        async for valkey in get_valkey_client():
            score = await valkey.zscore(k_fila, str(atend.id))  # pyright: ignore[reportUnknownMemberType]
            assert score is not None
            assert score > 0
    finally:
        await close_valkey_pool()


@pytest.mark.asyncio
async def test_end_to_end_private_eligibility_approved() -> None:
    """Private insurance approved by gateway promotes attendance
    and ingests in queue.
    """
    unidade = make_configuracao_unidade(modo_publico_sus=False)
    patient = make_paciente()
    atend = make_atendimento(
        paciente_id=patient.id,
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash=_VALID_TCLE_HASH,
    )

    async with async_session_factory() as session:
        session.add_all([unidade, patient, atend])
        await session.commit()

    mock_provider = AsyncMock(spec=EligibilityProviderPort)
    mock_provider.verificar_elegibilidade.return_value = ResultadoElegibilidade(
        aprovado=True,
        status=StatusElegibilidade.APROVADO,
        codigo_autorizacao="SULAMERICA-AUTH-77",
    )

    ctx: dict[str, Any] = {}
    await startup(ctx)
    try:
        result = await validar_elegibilidade_task(
            ctx,
            atendimento_id=str(atend.id),
            paciente_id=str(patient.id),
            provider=mock_provider,
        )

        assert result["status"] == "aprovado"
        assert result["aprovado"] is True
        assert result["codigo_autorizacao"] == "SULAMERICA-AUTH-77"

        # Verify DB state
        async with async_session_factory() as session:
            refreshed = await session.get(Atendimento, atend.id)
            assert refreshed is not None
            assert refreshed.status == StatusAtendimento.APTO_PARA_CHAMADA.value

        # Verify Valkey queue
        k_fila = "fila:aptos"
        async for valkey in get_valkey_client():
            score = await valkey.zscore(k_fila, str(atend.id))  # pyright: ignore[reportUnknownMemberType]
            assert score is not None
    finally:
        await close_valkey_pool()


@pytest.mark.asyncio
async def test_end_to_end_private_eligibility_rejected_preserves_queue_position() -> (
    None
):
    """Rejection leaves attendance in TRIADO_AGUARDANDO_ELEGIBILIDADE
    without expelling (RF-05).
    """
    unidade = make_configuracao_unidade(modo_publico_sus=False)
    patient = make_paciente()
    atend = make_atendimento(
        paciente_id=patient.id,
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash=_VALID_TCLE_HASH,
    )

    async with async_session_factory() as session:
        session.add_all([unidade, patient, atend])
        await session.commit()

    mock_provider = AsyncMock(spec=EligibilityProviderPort)
    mock_provider.verificar_elegibilidade.return_value = ResultadoElegibilidade(
        aprovado=False,
        status=StatusElegibilidade.REJEITADO,
        motivo="Plano cancelado",
    )

    ctx: dict[str, Any] = {}
    await startup(ctx)
    try:
        result = await validar_elegibilidade_task(
            ctx,
            atendimento_id=str(atend.id),
            paciente_id=str(patient.id),
            provider=mock_provider,
        )

        assert result["aprovado"] is False
        assert result["status"] == "REJEITADO"
        assert result["motivo"] == "Plano cancelado"

        # Verify DB status is strictly preserved (RF-05)
        async with async_session_factory() as session:
            refreshed = await session.get(Atendimento, atend.id)
            assert refreshed is not None
            assert (
                refreshed.status
                == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
            )

        # Verify not in Valkey ZSET
        k_fila = "fila:aptos"
        async for valkey in get_valkey_client():
            score = await valkey.zscore(k_fila, str(atend.id))  # pyright: ignore[reportUnknownMemberType]
            assert score is None
    finally:
        await close_valkey_pool()
