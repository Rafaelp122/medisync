"""Periodic self-healing sweeper reconciling PostgreSQL queue with Valkey (RN03)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text

from src.core.context import tenant_context
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.modules.queue.domain.scoring import calcular_score as calcular_score_fila
from src.worker.context import get_db_session_from_ctx, get_valkey_from_ctx
from src.worker.tasks.base import monitored_task

logger = logging.getLogger("medisync.worker.sweeper")


@monitored_task
async def reconciliar_fila_orphans_task(
    ctx: dict[str, Any],
    organizacao_id: int | None = None,
    threshold_segundos: int = 60,
) -> dict[str, Any]:
    """Sweeps PostgreSQL for APTO_PARA_CHAMADA attendances missing from Valkey.

    Mitigates dual-write inconsistency (e.g. process crashes or network drops
    after database commit or before queue ingestion):
    1. Scans active organizations (or targeted organizacao_id).
    2. Under tenant_context(org_id), queries attendances in status
       APTO_PARA_CHAMADA updated at or before (now - threshold_segundos).
    3. Checks Valkey:
       - If already present in ZSET fila:{org}:aptos -> skips.
       - If active ring lock lock:{org}:atendimento:{id} exists -> skips.
       - If assigned doctor has active consultation lock -> skips.
    4. If truly orphaned, recalculates original 64-bit score and reinjects
       into fila:{org}:aptos via ZADD.
    """
    valkey = get_valkey_from_ctx(ctx)
    cutoff = datetime.now(UTC) - timedelta(seconds=threshold_segundos)

    target_org_ids: list[int] = []
    if organizacao_id is not None:
        target_org_ids = [organizacao_id]
    else:
        async with get_db_session_from_ctx(ctx) as session:
            stmt_orgs = text("SELECT id FROM organizacoes WHERE ativo = true")
            result = await session.execute(stmt_orgs)
            target_org_ids = [int(row[0]) for row in result.fetchall()]

    total_scanned = 0
    total_reconciled = 0
    reconciled_ids: list[str] = []

    for org_id in target_org_ids:
        k_fila = f"fila:{org_id}:aptos"

        with tenant_context(org_id):
            async with get_db_session_from_ctx(ctx) as session:
                stmt_orphans = (
                    select(Atendimento)
                    .where(
                        Atendimento.organizacao_id == org_id,
                        Atendimento.status == StatusAtendimento.APTO_PARA_CHAMADA.value,
                        Atendimento.atualizado_em <= cutoff,
                    )
                    .order_by(Atendimento.criado_em.asc())
                )
                candidates = (await session.execute(stmt_orphans)).scalars().all()

                for atend in candidates:
                    total_scanned += 1
                    atend_id_str = str(atend.id)

                    # 1. Check if already present in Valkey ZSET
                    existing_score = await valkey.zscore(  # pyright: ignore[reportUnknownMemberType]
                        k_fila, atend_id_str
                    )
                    if existing_score is not None:
                        continue

                    # 2. Check if active ring lock exists
                    k_atend_ring = f"lock:{org_id}:atendimento:{atend_id_str}"
                    has_ring_lock = bool(
                        await valkey.exists(k_atend_ring)  # pyright: ignore[reportUnknownMemberType]
                    )
                    if has_ring_lock:
                        continue

                    # 3. Check if active consultation lock exists for assigned doctor
                    if atend.medico_id is not None:
                        med_id_str = str(atend.medico_id)
                        k_med_ring = f"lock:{org_id}:medico:{med_id_str}"
                        k_med_active = (
                            f"lock:{org_id}:consulta_ativa:medico:{med_id_str}"
                        )
                        med_ring_val = await valkey.get(k_med_ring)  # pyright: ignore[reportUnknownMemberType]
                        med_active_val = await valkey.get(k_med_active)  # pyright: ignore[reportUnknownMemberType]
                        if (
                            med_ring_val == atend_id_str.encode()
                            or med_ring_val == atend_id_str
                            or med_active_val == atend_id_str.encode()
                            or med_active_val == atend_id_str
                        ):
                            continue

                    # 4. Truly orphaned -> recalculate score and reinject into ZSET
                    ts_base = atend.data_entrada_fila or atend.criado_em
                    score = calcular_score_fila(atend.prioridade_clinica, ts_base)

                    await valkey.zadd(k_fila, {atend_id_str: score})  # pyright: ignore[reportUnknownMemberType]
                    total_reconciled += 1
                    reconciled_ids.append(atend_id_str)

                    logger.warning(
                        "Sweeper restored orphan attendance %s to %s with score=%d",
                        atend_id_str,
                        k_fila,
                        score,
                        extra={
                            "organizacao_id": org_id,
                            "atendimento_id": atend_id_str,
                            "prioridade_clinica": atend.prioridade_clinica,
                            "score": score,
                        },
                    )

    logger.info(
        "Sweeper queue reconciliation finished: orgs=%d scanned=%d reconciled=%d",
        len(target_org_ids),
        total_scanned,
        total_reconciled,
    )

    return {
        "status": "success",
        "scanned_organizations": len(target_org_ids),
        "scanned_appointments": total_scanned,
        "reconciled_appointments": total_reconciled,
        "reconciled_ids": reconciled_ids,
    }
