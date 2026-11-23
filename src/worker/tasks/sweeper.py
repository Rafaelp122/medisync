"""Periodic self-healing sweeper reconciling PostgreSQL queue with Valkey (RN03)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis

from src.modules.queue.application.ports.queue_engine_port import QueueEnginePort
from src.modules.queue.composition import (
    build_fila_service_for_session,
    build_queue_engine,
)
from src.worker.context import get_db_session_from_ctx, get_valkey_from_ctx
from src.worker.tasks.base import monitored_task

logger = logging.getLogger("medisync.worker.sweeper")

_SWEEPER_BATCH_SIZE = 200
_SWEEPER_LOCK_TTL_SEGUNDOS = 55


async def _executar_sweeper_protegido(
    *,
    ctx: dict[str, Any],
    valkey: Redis,
    engine: QueueEnginePort,
    cutoff: datetime,
) -> tuple[int, list[str]]:
    try:
        async with get_db_session_from_ctx(ctx) as session:
            fila_service = build_fila_service_for_session(
                valkey=valkey,
                session=session,
                queue_engine=engine,
            )
            return await fila_service.reconciliar_fila_orfaos(
                cutoff_em=cutoff,
                batch_size=_SWEEPER_BATCH_SIZE,
            )
    finally:
        await engine.liberar_lock_sweeper()


@monitored_task
async def reconciliar_fila_orphans_task(
    ctx: dict[str, Any],
    threshold_segundos: int = 60,
) -> dict[str, Any]:
    """Sweeps PostgreSQL for APTO attendances missing from Valkey under lock.

    Acquires lock:sweeper:fila_aptos (NX EX 55), iterates keyset batches of 200 rows,
    and reinjects verified orphans safely using ZADD NX.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=threshold_segundos)

    async with get_valkey_from_ctx(ctx) as valkey:
        engine = build_queue_engine(valkey=valkey)
        if not await engine.adquirir_lock_sweeper(
            ttl_segundos=_SWEEPER_LOCK_TTL_SEGUNDOS
        ):
            logger.info(
                "Sweeper queue reconciliation skipped: distributed lock already held"
            )
            return {
                "status": "skipped",
                "reason": "lock_held",
                "scanned_appointments": 0,
                "reconciled_appointments": 0,
                "reconciled_ids": [],
            }

        total_scanned, reconciled_ids = await _executar_sweeper_protegido(
            ctx=ctx,
            valkey=valkey,
            engine=engine,
            cutoff=cutoff,
        )

    total_reconciled = len(reconciled_ids)
    logger.info(
        "Sweeper queue reconciliation finished: scanned=%d reconciled=%d",
        total_scanned,
        total_reconciled,
    )
    return {
        "status": "success",
        "scanned_appointments": total_scanned,
        "reconciled_appointments": total_reconciled,
        "reconciled_ids": reconciled_ids,
    }
