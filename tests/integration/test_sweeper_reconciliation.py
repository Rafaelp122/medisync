"""Integration tests for periodic sweeper self-healing queue reconciliation (RN03)."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from src.core.context import tenant_context
from src.core.database import Base, async_session_factory, engine
from src.core.valkey import close_valkey_pool, get_valkey_client
from src.modules.queue.domain.models import PrioridadeClinica
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.modules.queue.domain.scoring import calcular_score
from src.worker.settings import startup
from src.worker.tasks.sweeper import reconciliar_fila_orphans_task

from tests.factories.identity import make_organizacao, make_paciente
from tests.factories.queue import make_atendimento

_TEST_ORG_ID = 888


@pytest.fixture(autouse=True)
async def clean_database_and_valkey() -> AsyncGenerator[None]:
    """Ensure clean PostgreSQL tables and Valkey keys for each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "TRUNCATE TABLE atendimentos, dependentes, pacientes, "
                "profissionais, organizacoes CASCADE;"
            )
        )

    yield

    async for client in get_valkey_client():
        keys = await client.keys(f"lock:{_TEST_ORG_ID}:*")  # pyright: ignore[reportUnknownMemberType]
        keys.extend(await client.keys(f"fila:{_TEST_ORG_ID}:*"))  # pyright: ignore[reportUnknownMemberType]
        keys.extend(await client.keys("arq:*"))  # pyright: ignore[reportUnknownMemberType]
        if keys:
            await client.delete(*keys)

    await close_valkey_pool()


@pytest.mark.asyncio
async def test_end_to_end_sweeper_restores_orphaned_appointment() -> None:
    """Orphaned attendance missing from Valkey ZSET is restored with exact score."""
    org = make_organizacao(id=_TEST_ORG_ID)
    patient = make_paciente(organizacao_id=org.id)

    entrada = datetime.now(UTC) - timedelta(seconds=120)
    atend = make_atendimento(
        organizacao_id=org.id,
        paciente_id=patient.id,
        status=StatusAtendimento.APTO_PARA_CHAMADA.value,
        prioridade_clinica=PrioridadeClinica.MUITO_URGENTE,
        data_entrada_fila=entrada,
    )

    with tenant_context(org.id):
        async with async_session_factory() as session:
            session.add_all([org, patient, atend])
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
    k_fila = f"fila:{org.id}:aptos"
    async for valkey in get_valkey_client():
        initial_score = await valkey.zscore(k_fila, str(atend.id))  # pyright: ignore[reportUnknownMemberType]
        assert initial_score is None

    # Execute sweeper task
    ctx: dict[str, Any] = {}
    await startup(ctx)
    try:
        result = await reconciliar_fila_orphans_task(
            ctx,
            organizacao_id=org.id,
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
    finally:
        await close_valkey_pool()


@pytest.mark.asyncio
async def test_end_to_end_sweeper_protects_in_flight_ring_call() -> None:
    """Active in-flight call (ring lock active) is never reinjected into queue."""
    org = make_organizacao(id=_TEST_ORG_ID)
    patient = make_paciente(organizacao_id=org.id)

    entrada = datetime.now(UTC) - timedelta(seconds=120)
    atend = make_atendimento(
        organizacao_id=org.id,
        paciente_id=patient.id,
        status=StatusAtendimento.APTO_PARA_CHAMADA.value,
        prioridade_clinica=PrioridadeClinica.POUCO_URGENTE,
        data_entrada_fila=entrada,
    )

    with tenant_context(org.id):
        async with async_session_factory() as session:
            session.add_all([org, patient, atend])
            await session.commit()
            await session.execute(
                text(
                    "UPDATE atendimentos SET atualizado_em = :past WHERE id = :atend_id"
                ),
                {"past": entrada, "atend_id": atend.id},
            )
            await session.commit()

    # Set active ring lock in Valkey
    k_fila = f"fila:{org.id}:aptos"
    k_ring = f"lock:{org.id}:atendimento:{atend.id}"
    async for valkey in get_valkey_client():
        await valkey.set(k_ring, "doctor-temp-lock", ex=45)

    # Execute sweeper task
    ctx: dict[str, Any] = {}
    await startup(ctx)
    try:
        result = await reconciliar_fila_orphans_task(
            ctx,
            organizacao_id=org.id,
            threshold_segundos=60,
        )

        assert result["scanned_appointments"] == 1
        assert result["reconciled_appointments"] == 0

        # Verify not reinjected into Valkey
        async for valkey in get_valkey_client():
            score = await valkey.zscore(k_fila, str(atend.id))  # pyright: ignore[reportUnknownMemberType]
            assert score is None
    finally:
        await close_valkey_pool()


@pytest.mark.asyncio
async def test_end_to_end_sweeper_idempotent_when_already_in_queue() -> None:
    """Idempotent behavior: already queued attendances remain unaffected."""
    org = make_organizacao(id=_TEST_ORG_ID)
    patient = make_paciente(organizacao_id=org.id)

    entrada = datetime.now(UTC) - timedelta(seconds=120)
    atend = make_atendimento(
        organizacao_id=org.id,
        paciente_id=patient.id,
        status=StatusAtendimento.APTO_PARA_CHAMADA.value,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        data_entrada_fila=entrada,
    )

    with tenant_context(org.id):
        async with async_session_factory() as session:
            session.add_all([org, patient, atend])
            await session.commit()
            await session.execute(
                text(
                    "UPDATE atendimentos SET atualizado_em = :past WHERE id = :atend_id"
                ),
                {"past": entrada, "atend_id": atend.id},
            )
            await session.commit()

    # Pre-populate Valkey ZSET
    k_fila = f"fila:{org.id}:aptos"
    expected_score = calcular_score(PrioridadeClinica.URGENTE, entrada)
    async for valkey in get_valkey_client():
        await valkey.zadd(k_fila, {str(atend.id): expected_score})  # pyright: ignore[reportUnknownMemberType]

    # Execute sweeper task
    ctx: dict[str, Any] = {}
    await startup(ctx)
    try:
        result = await reconciliar_fila_orphans_task(
            ctx,
            organizacao_id=org.id,
            threshold_segundos=60,
        )

        assert result["scanned_appointments"] == 1
        assert result["reconciled_appointments"] == 0

        # Verify score is intact and count is 1
        async for valkey in get_valkey_client():
            card = await valkey.zcard(k_fila)  # pyright: ignore[reportUnknownMemberType]
            assert card == 1
    finally:
        await close_valkey_pool()
