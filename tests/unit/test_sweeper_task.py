"""Unit tests for periodic self-healing sweeper task (RN03)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from src.modules.queue.domain.models import Atendimento, PrioridadeClinica
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.modules.queue.domain.scoring import calcular_score
from src.modules.queue.infrastructure.valkey_queue_engine import (
    FILA_APTOS_KEY,
    SWEEPER_LOCK_KEY,
)
from src.worker.tasks.sweeper import reconciliar_fila_orphans_task

from tests.doubles import (
    FakeAsyncSession,
    FakeAsyncSessionFactory,
    FakeResult,
    FakeValkey,
)

_SAMPLE_TCLE = "a" * 64


def _create_worker_context(
    session: FakeAsyncSession,
    valkey: FakeValkey,
) -> dict[str, Any]:
    return {
        "db_session_factory": FakeAsyncSessionFactory(session),
        "valkey_client": valkey,
    }


def _make_apto_orphan(entrada: datetime, *, medico_id: Any = None) -> Atendimento:
    return Atendimento(
        id=uuid4(),
        paciente_id=uuid4(),
        medico_id=medico_id,
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash=_SAMPLE_TCLE,
        data_entrada_fila=entrada,
        criado_em=entrada,
        atualizado_em=entrada,
    )


@pytest.mark.asyncio
async def test_reconciliar_fila_orphans_restores_missing_attendance() -> None:
    """Orphan attendance missing from ZSET with no locks is reinjected and unlocked."""
    entrada = datetime.now(UTC) - timedelta(seconds=120)
    atend = _make_apto_orphan(entrada)

    fake_session = FakeAsyncSession(
        results=[
            FakeResult([atend]),
            FakeResult(StatusAtendimento.APTO_PARA_CHAMADA.value),
            FakeResult([]),
        ]
    )
    fake_valkey = FakeValkey()
    ctx = _create_worker_context(fake_session, fake_valkey)

    result: dict[str, Any] = await reconciliar_fila_orphans_task(
        ctx,
        threshold_segundos=60,
    )

    assert result["status"] == "success"
    assert "scanned_organizations" not in result
    assert result["scanned_appointments"] == 1
    assert result["reconciled_appointments"] == 1
    assert result["reconciled_ids"] == [str(atend.id)]

    expected_score = calcular_score(PrioridadeClinica.URGENTE, entrada)
    assert await fake_valkey.zscore(FILA_APTOS_KEY, str(atend.id)) == float(
        expected_score
    )
    assert await fake_valkey.exists(SWEEPER_LOCK_KEY) == 0


@pytest.mark.asyncio
async def test_reconciliar_fila_orphans_skips_when_distributed_lock_held() -> None:
    """Concurrent sweeper execution skips gracefully when distributed lock is held."""
    fake_session = FakeAsyncSession()
    fake_valkey = FakeValkey()
    await fake_valkey.set(SWEEPER_LOCK_KEY, "1", nx=True)

    ctx = _create_worker_context(fake_session, fake_valkey)
    result: dict[str, Any] = await reconciliar_fila_orphans_task(
        ctx,
        threshold_segundos=60,
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "lock_held"
    assert result["scanned_appointments"] == 0
    assert result["reconciled_appointments"] == 0
    assert fake_session.executes == 0
    assert await fake_valkey.exists(SWEEPER_LOCK_KEY) == 1


@pytest.mark.asyncio
async def test_reconciliar_fila_orphans_skips_when_already_in_zset() -> None:
    """Attendance already present in Valkey ZSET is not reinjected."""
    entrada = datetime.now(UTC) - timedelta(seconds=120)
    atend = _make_apto_orphan(entrada)

    fake_session = FakeAsyncSession(results=[FakeResult([atend]), FakeResult([])])
    fake_valkey = FakeValkey()
    await fake_valkey.zadd(FILA_APTOS_KEY, {str(atend.id): 3000000000000})

    ctx = _create_worker_context(fake_session, fake_valkey)
    result: dict[str, Any] = await reconciliar_fila_orphans_task(
        ctx,
        threshold_segundos=60,
    )

    assert result["scanned_appointments"] == 1
    assert result["reconciled_appointments"] == 0
    assert await fake_valkey.zscore(FILA_APTOS_KEY, str(atend.id)) == 3000000000000.0
    assert await fake_valkey.exists(SWEEPER_LOCK_KEY) == 0


@pytest.mark.asyncio
async def test_reconciliar_fila_orphans_skips_when_ring_lock_active() -> None:
    """Attendance currently in ringing state (lock active) is not reinjected."""
    entrada = datetime.now(UTC) - timedelta(seconds=120)
    atend = _make_apto_orphan(entrada)

    fake_session = FakeAsyncSession(results=[FakeResult([atend]), FakeResult([])])
    fake_valkey = FakeValkey()
    await fake_valkey.set(f"lock:atendimento:{atend.id}", "doctor-id")

    ctx = _create_worker_context(fake_session, fake_valkey)
    result: dict[str, Any] = await reconciliar_fila_orphans_task(
        ctx,
        threshold_segundos=60,
    )

    assert result["scanned_appointments"] == 1
    assert result["reconciled_appointments"] == 0
    assert await fake_valkey.zscore(FILA_APTOS_KEY, str(atend.id)) is None


@pytest.mark.asyncio
async def test_reconciliar_fila_orphans_skips_when_consultation_lock_active() -> None:
    """Attendance associated with active consultation is not reinjected."""
    entrada = datetime.now(UTC) - timedelta(seconds=120)
    medico_id = uuid4()
    atend = _make_apto_orphan(entrada, medico_id=medico_id)

    fake_session = FakeAsyncSession(results=[FakeResult([atend]), FakeResult([])])
    fake_valkey = FakeValkey()
    await fake_valkey.set(f"lock:consulta_ativa:medico:{medico_id}", str(atend.id))

    ctx = _create_worker_context(fake_session, fake_valkey)
    result: dict[str, Any] = await reconciliar_fila_orphans_task(
        ctx,
        threshold_segundos=60,
    )

    assert result["scanned_appointments"] == 1
    assert result["reconciled_appointments"] == 0
    assert await fake_valkey.zscore(FILA_APTOS_KEY, str(atend.id)) is None


@pytest.mark.asyncio
async def test_reconciliar_fila_orphans_revalida_status_antes_zadd_nx() -> None:
    """Attendance allocated concurrently (status changed in DB) is NOT reinjected."""
    entrada = datetime.now(UTC) - timedelta(seconds=120)
    atend = _make_apto_orphan(entrada)

    fake_session = FakeAsyncSession(
        results=[
            FakeResult([atend]),
            FakeResult(StatusAtendimento.CHAMANDO_PACIENTE.value),
            FakeResult([]),
        ]
    )
    fake_valkey = FakeValkey()
    ctx = _create_worker_context(fake_session, fake_valkey)

    result: dict[str, Any] = await reconciliar_fila_orphans_task(
        ctx,
        threshold_segundos=60,
    )

    assert result["scanned_appointments"] == 1
    assert result["reconciled_appointments"] == 0
    assert await fake_valkey.zscore(FILA_APTOS_KEY, str(atend.id)) is None


@pytest.mark.asyncio
async def test_reconciliar_fila_orphans_paginado_multiplos_lotes_e_cleanup_lock() -> (
    None
):
    """Sweeper processes paginated batches and always releases lock in finally."""
    entrada_1 = datetime.now(UTC) - timedelta(seconds=180)
    entrada_2 = datetime.now(UTC) - timedelta(seconds=120)
    atend_1 = _make_apto_orphan(entrada_1)
    atend_2 = _make_apto_orphan(entrada_2)

    fake_session = FakeAsyncSession(
        results=[
            FakeResult([atend_1]),
            FakeResult(StatusAtendimento.APTO_PARA_CHAMADA.value),
            FakeResult([atend_2]),
            FakeResult(StatusAtendimento.APTO_PARA_CHAMADA.value),
            FakeResult([]),
        ]
    )
    fake_valkey = FakeValkey()
    ctx = _create_worker_context(fake_session, fake_valkey)

    result: dict[str, Any] = await reconciliar_fila_orphans_task(
        ctx,
        threshold_segundos=60,
    )

    assert result["status"] == "success"
    assert result["scanned_appointments"] == 2
    assert result["reconciled_appointments"] == 2
    assert result["reconciled_ids"] == [str(atend_1.id), str(atend_2.id)]
    assert await fake_valkey.exists(SWEEPER_LOCK_KEY) == 0


@pytest.mark.asyncio
async def test_reconciliar_fila_orphans_empty_queue_returns_zero_counts() -> None:
    """When no candidate attendances exist, sweeper returns zero counts cleanly."""
    fake_session = FakeAsyncSession(results=[FakeResult([])])
    fake_valkey = FakeValkey()
    ctx = _create_worker_context(fake_session, fake_valkey)

    result: dict[str, Any] = await reconciliar_fila_orphans_task(
        ctx,
        threshold_segundos=60,
    )

    assert result["status"] == "success"
    assert result["scanned_appointments"] == 0
    assert result["reconciled_appointments"] == 0
    assert result["reconciled_ids"] == []
    assert await fake_valkey.exists(SWEEPER_LOCK_KEY) == 0
