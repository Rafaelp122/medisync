"""Integration tests for periodic sweeper self-healing queue reconciliation (RN03)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from src.core.database import get_session_factory
from src.core.valkey import get_valkey_client
from src.modules.queue.domain.models import PrioridadeClinica
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.modules.queue.domain.scoring import calcular_score
from src.worker.settings import startup
from src.worker.tasks.sweeper import reconciliar_fila_orphans_task

from tests.factories.scenarios import seed_clinical_scenario

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_end_to_end_sweeper_restores_orphaned_appointment() -> None:
    """Orphaned attendance missing from Valkey ZSET is restored with exact score."""
    entrada = datetime.now(UTC) - timedelta(seconds=120)
    async with get_session_factory()() as session:
        cenario = await seed_clinical_scenario(
            session,
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
            text("UPDATE atendimentos SET atualizado_em = :past WHERE id = :atend_id"),
            {"past": entrada, "atend_id": atend.id},
        )
        await session.commit()

    # Valkey ZSET is currently empty
    k_fila = "fila:aptos"
    async for valkey in get_valkey_client():
        initial_score = await valkey.zscore(k_fila, str(atend.id))  # pyright: ignore[reportUnknownMemberType]
        assert initial_score is None

    # Execute sweeper task
    ctx: dict[str, Any] = {}
    await startup(ctx)
    result = await reconciliar_fila_orphans_task(ctx, threshold_segundos=60)

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
    async with get_session_factory()() as session:
        cenario = await seed_clinical_scenario(
            session,
            status_atendimento=StatusAtendimento.APTO_PARA_CHAMADA,
            prioridade_clinica=PrioridadeClinica.POUCO_URGENTE,
        )
        atend = cenario.atendimento
        atend.medico_id = None
        atend.data_entrada_fila = entrada
        session.add(atend)
        await session.commit()
        await session.execute(
            text("UPDATE atendimentos SET atualizado_em = :past WHERE id = :atend_id"),
            {"past": entrada, "atend_id": atend.id},
        )
        await session.commit()

    # Set active ring lock in Valkey
    k_fila = "fila:aptos"
    k_ring = f"lock:atendimento:{atend.id}"
    async for valkey in get_valkey_client():
        await valkey.set(k_ring, "doctor-temp-lock", ex=45)

    # Execute sweeper task
    ctx: dict[str, Any] = {}
    await startup(ctx)
    result = await reconciliar_fila_orphans_task(ctx, threshold_segundos=60)

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
    async with get_session_factory()() as session:
        cenario = await seed_clinical_scenario(
            session,
            status_atendimento=StatusAtendimento.APTO_PARA_CHAMADA,
            prioridade_clinica=PrioridadeClinica.URGENTE,
        )
        atend = cenario.atendimento
        atend.medico_id = None
        atend.data_entrada_fila = entrada
        session.add(atend)
        await session.commit()
        await session.execute(
            text("UPDATE atendimentos SET atualizado_em = :past WHERE id = :atend_id"),
            {"past": entrada, "atend_id": atend.id},
        )
        await session.commit()

    # Pre-populate Valkey ZSET
    k_fila = "fila:aptos"
    expected_score = calcular_score(PrioridadeClinica.URGENTE, entrada)
    async for valkey in get_valkey_client():
        await valkey.zadd(k_fila, {str(atend.id): expected_score})  # pyright: ignore[reportUnknownMemberType]

    # Execute sweeper task
    ctx: dict[str, Any] = {}
    await startup(ctx)
    result = await reconciliar_fila_orphans_task(ctx, threshold_segundos=60)

    assert result["scanned_appointments"] == 1
    assert result["reconciled_appointments"] == 0

    # Verify score is intact and count is 1
    async for valkey in get_valkey_client():
        card = await valkey.zcard(k_fila)  # pyright: ignore[reportUnknownMemberType]
        assert card == 1


@pytest.mark.asyncio
async def test_end_to_end_sweeper_skips_when_distributed_lock_held() -> None:
    """Concurrent sweeper skips gracefully when distributed lock is held."""
    from src.modules.queue.infrastructure.valkey_queue_engine import SWEEPER_LOCK_KEY

    entrada = datetime.now(UTC) - timedelta(seconds=120)
    async with get_session_factory()() as session:
        cenario = await seed_clinical_scenario(
            session,
            status_atendimento=StatusAtendimento.APTO_PARA_CHAMADA,
            prioridade_clinica=PrioridadeClinica.URGENTE,
        )
        atend = cenario.atendimento
        atend.medico_id = None
        atend.data_entrada_fila = entrada
        session.add(atend)
        await session.commit()
        await session.execute(
            text("UPDATE atendimentos SET atualizado_em = :past WHERE id = :atend_id"),
            {"past": entrada, "atend_id": atend.id},
        )
        await session.commit()

    async for valkey in get_valkey_client():
        await valkey.set(SWEEPER_LOCK_KEY, "other-worker", nx=True, ex=55)

    ctx: dict[str, Any] = {}
    await startup(ctx)
    result = await reconciliar_fila_orphans_task(ctx, threshold_segundos=60)

    assert result["status"] == "skipped"
    assert result["reason"] == "lock_held"
    assert result["scanned_appointments"] == 0

    async for valkey in get_valkey_client():
        assert await valkey.zscore("fila:aptos", str(atend.id)) is None  # pyright: ignore[reportUnknownMemberType]
        assert await valkey.get(SWEEPER_LOCK_KEY) == "other-worker"
