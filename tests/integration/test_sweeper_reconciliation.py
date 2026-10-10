"""Integration tests for periodic sweeper self-healing queue reconciliation (RN03)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from src.core.context import tenant_context
from src.core.database import async_session_factory
from src.core.valkey import get_valkey_client
from src.modules.queue.domain.models import PrioridadeClinica
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.modules.queue.domain.scoring import calcular_score
from src.worker.settings import startup
from src.worker.tasks.sweeper import reconciliar_fila_orphans_task

from tests.factories.scenarios import seed_clinical_scenario

_TEST_ORG_ID = 888

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_end_to_end_sweeper_restores_orphaned_appointment() -> None:
    """Orphaned attendance missing from Valkey ZSET is restored with exact score."""
    entrada = datetime.now(UTC) - timedelta(seconds=120)
    with tenant_context(_TEST_ORG_ID):
        async with async_session_factory() as session:
            cenario = await seed_clinical_scenario(
                session,
                org_id=_TEST_ORG_ID,
                status_atendimento=StatusAtendimento.APTO_PARA_CHAMADA,
                prioridade_clinica=PrioridadeClinica.MUITO_URGENTE,
            )
            atend = cenario.atendimento
            atend.medico_id = None
            atend.data_entrada_fila = entrada
            session.add(atend)
            await session.commit()

            # Ensure atualizado_em is older than 60 seconds
            await session.execute(
                text(
                    "UPDATE atendimentos SET atualizado_em = :past WHERE id = :atend_id"
                ),
                {"past": entrada, "atend_id": atend.id},
            )
            await session.commit()

    # Valkey ZSET is currently empty
    k_fila = f"fila:{_TEST_ORG_ID}:aptos"
    async for valkey in get_valkey_client():
        initial_score = await valkey.zscore(k_fila, str(atend.id))  # pyright: ignore[reportUnknownMemberType]
        assert initial_score is None

    # Execute sweeper task
    ctx: dict[str, Any] = {}
    await startup(ctx)
    result = await reconciliar_fila_orphans_task(
        ctx,
        organizacao_id=_TEST_ORG_ID,
        threshold_segundos=60,
    )

    assert result["status"] == "success"
    assert result["reconciled_appointments"] == 1
    assert result["reconciled_ids"] == [str(atend.id)]

    # Verify restored into Valkey with deterministic 64-bit score
    async for valkey in get_valkey_client():
        restored_score = await valkey.zscore(k_fila, str(atend.id))  # pyright: ignore[reportUnknownMemberType]
        expected_score = calcular_score(PrioridadeClinica.MUITO_URGENTE, entrada)
        assert restored_score is not None
        assert int(restored_score) == expected_score


@pytest.mark.asyncio
async def test_end_to_end_sweeper_protects_in_flight_ring_call() -> None:
    """Active in-flight call (ring lock active) is never reinjected into queue."""
    entrada = datetime.now(UTC) - timedelta(seconds=120)
    with tenant_context(_TEST_ORG_ID):
        async with async_session_factory() as session:
            cenario = await seed_clinical_scenario(
                session,
                org_id=_TEST_ORG_ID,
                status_atendimento=StatusAtendimento.APTO_PARA_CHAMADA,
                prioridade_clinica=PrioridadeClinica.POUCO_URGENTE,
            )
            atend = cenario.atendimento
            atend.medico_id = None
            atend.data_entrada_fila = entrada
            session.add(atend)
            await session.commit()
            await session.execute(
                text(
                    "UPDATE atendimentos SET atualizado_em = :past WHERE id = :atend_id"
                ),
                {"past": entrada, "atend_id": atend.id},
            )
            await session.commit()

    # Set active ring lock in Valkey
    k_fila = f"fila:{_TEST_ORG_ID}:aptos"
    k_ring = f"lock:{_TEST_ORG_ID}:atendimento:{atend.id}"
    async for valkey in get_valkey_client():
        await valkey.set(k_ring, "doctor-temp-lock", ex=45)

    # Execute sweeper task
    ctx: dict[str, Any] = {}
    await startup(ctx)
    result = await reconciliar_fila_orphans_task(
        ctx,
        organizacao_id=_TEST_ORG_ID,
        threshold_segundos=60,
    )

    assert result["scanned_appointments"] == 1
    assert result["reconciled_appointments"] == 0

    # Verify not reinjected into Valkey
    async for valkey in get_valkey_client():
        score = await valkey.zscore(k_fila, str(atend.id))  # pyright: ignore[reportUnknownMemberType]
        assert score is None


@pytest.mark.asyncio
async def test_end_to_end_sweeper_idempotent_when_already_in_queue() -> None:
    """Idempotent behavior: already queued attendances remain unaffected."""
    entrada = datetime.now(UTC) - timedelta(seconds=120)
    with tenant_context(_TEST_ORG_ID):
        async with async_session_factory() as session:
            cenario = await seed_clinical_scenario(
                session,
                org_id=_TEST_ORG_ID,
                status_atendimento=StatusAtendimento.APTO_PARA_CHAMADA,
                prioridade_clinica=PrioridadeClinica.URGENTE,
            )
            atend = cenario.atendimento
            atend.medico_id = None
            atend.data_entrada_fila = entrada
            session.add(atend)
            await session.commit()
            await session.execute(
                text(
                    "UPDATE atendimentos SET atualizado_em = :past WHERE id = :atend_id"
                ),
                {"past": entrada, "atend_id": atend.id},
            )
            await session.commit()

    # Pre-populate Valkey ZSET
    k_fila = f"fila:{_TEST_ORG_ID}:aptos"
    expected_score = calcular_score(PrioridadeClinica.URGENTE, entrada)
    async for valkey in get_valkey_client():
        await valkey.zadd(k_fila, {str(atend.id): expected_score})  # pyright: ignore[reportUnknownMemberType]

    # Execute sweeper task
    ctx: dict[str, Any] = {}
    await startup(ctx)
    result = await reconciliar_fila_orphans_task(
        ctx,
        organizacao_id=_TEST_ORG_ID,
        threshold_segundos=60,
    )

    assert result["scanned_appointments"] == 1
    assert result["reconciled_appointments"] == 0

    # Verify score is intact and count is 1
    async for valkey in get_valkey_client():
        card = await valkey.zcard(k_fila)  # pyright: ignore[reportUnknownMemberType]
        assert card == 1
